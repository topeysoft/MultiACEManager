"""
Hot-plug: a unit that was off or still booting when Klipper started is picked up once it
has been seen twice on the same USB enumeration, without a Klipper restart. A unit that
gave up retrying is reconnected when its port is back. A unit nobody talks to reboots
every ~3.6 s, so it has to be caught inside one of those windows.
"""
import logging

import pytest

A = {"device_id": "hub_3_port_1_1_3_1_0", "usb_location": "3-1.1.3:1.0", "port": "/dev/ttyACE_A", "port_tty": "/dev/ttyACM2"}
B = {"device_id": "hub_3_port_1_3_3_1_0", "usb_location": "3-1.3.3:1.0", "port": "/dev/ttyACE_B", "port_tty": "/dev/ttyACM1"}


class _Mapper:
    def __init__(self, offsets=None):
        self.offsets = dict(offsets or {})
        self.saved = 0
    def get_all_devices(self):
        return {d: {"last_gate_offset": o} for d, o in self.offsets.items()}
    def get_all_aliases(self):
        return {}
    def update_device(self, device_id, port, usb_location=None, current_gate_offset=None, port_tty=None):
        self.offsets[device_id] = current_gate_offset
    def save(self):
        self.saved += 1


class _PrintStats:
    state = "standby"
    def get_status(self, eventtime):
        return {"state": self.state}


class _Gcode:
    def __init__(self):
        self.said = []
    def respond_info(self, msg):
        self.said.append(msg)


class _Printer:
    def __init__(self):
        self.objects = {"print_stats": _PrintStats(), "gcode": _Gcode()}
    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)


@pytest.fixture
def hp(ace, reactor, fake_serial):
    """A device manager with no units at startup and a scriptable USB bus."""
    from ace.device.device_manager import AceDeviceManager
    m = AceDeviceManager.__new__(AceDeviceManager)   # skip __init__ (needs Klipper config)
    m.printer = _Printer()
    m.reactor = reactor
    m.baud = 115200
    m.log_level = logging.INFO
    m.connect_retry_delay = 0.5
    m.connect_retry_max = 3
    m.device_mapper = _Mapper()
    m.device_order = []
    m.ace_devices = []
    m.device_ids = {}
    m.total_gates = 0
    m._auto_detect = True
    m._seen = {}
    m._next_hotplug = 0.0
    m.on_devices_changed = []
    m.is_tool_loaded = lambda: False
    bus = {}   # usb_location -> unit dict (what quick_scan would return)
    m._scan = lambda: [dict(u) for u in bus.values()]
    for unit in (A, B):
        fake_serial(unit["port"])
    return m, bus


def plug(bus, unit, devnum):
    bus[unit["usb_location"]] = dict(unit, devnum=devnum)


def look(m, reactor, seconds):
    """Let the hot-plug check run for ``seconds`` of printer time, every HOTPLUG_INTERVAL."""
    from ace.device.device_manager import HOTPLUG_INTERVAL
    end = reactor.monotonic() + seconds
    while reactor.monotonic() < end:
        reactor.advance(HOTPLUG_INTERVAL)
        m._hotplug_check(reactor.monotonic())


def boot_with(m, reactor, unit, offset=0):
    from ace.device.ace_device import AceDevice
    inst = AceDevice(port=unit["port"], baud=115200, device_id=unit["device_id"], reactor=reactor,
                     connect_retry_delay=0.5, connect_retry_max=3)
    m.ace_devices.append(dict(unit, name=f"ACE_{len(m.ace_devices) + 1}", instance=inst, gate_offset=offset))
    m.total_gates = len(m.ace_devices) * 4
    inst.connect()
    reactor.advance(0.1)
    return inst


def test_unit_is_picked_up_once_steady(hp, reactor):
    m, bus = hp
    plug(bus, A, devnum=40)
    m._hotplug_check(reactor.monotonic())
    assert m.ace_devices == [], "not on the first sighting"
    look(m, reactor, 1)
    assert [d["device_id"] for d in m.ace_devices] == [A["device_id"]]
    assert m.total_gates == 4 and m.ace_devices[0]["name"] == "ACE_1"
    reactor.advance(0.1)
    assert m.ace_devices[0]["instance"]._connected
    assert "found ACE_1" in m.printer.objects["gcode"].said[-1]
    assert m.device_mapper.offsets == {A["device_id"]: 0} and m.device_mapper.saved == 1


def test_unit_that_reboots_when_left_alone_is_caught_in_its_window(hp, reactor):
    """r2d2 and obi1, 2026-10-03: an ignored unit re-enumerates every ~3.6 s. The old 15 s
    steadiness rule meant it was never used; it must be connected well inside 3.5 s."""
    m, bus = hp
    plug(bus, A, devnum=40)
    look(m, reactor, 2.5)
    assert [d["device_id"] for d in m.ace_devices] == [A["device_id"]]


def test_unit_that_re_enumerated_between_looks_waits_for_a_second_sighting(hp, reactor):
    from ace.device.device_manager import HOTPLUG_INTERVAL
    m, bus = hp
    plug(bus, A, devnum=40)
    m._hotplug_check(reactor.monotonic())
    reactor.advance(HOTPLUG_INTERVAL)
    plug(bus, A, devnum=41)
    m._hotplug_check(reactor.monotonic())
    assert m.ace_devices == []


def test_manager_polls_at_keepalive_rate_even_with_nothing_connected(hp):
    """The hot-plug check runs on the I/O timer; a 30 s idle timer could never catch a
    unit that reboots every 3.6 s."""
    from ace.protocol.constants import KEEPALIVE_INTERVAL
    m, _ = hp
    m.adaptive_polling = True
    assert m._get_global_adaptive_interval() <= KEEPALIVE_INTERVAL


def test_never_added_during_a_print(hp, reactor):
    m, bus = hp
    m.printer.objects["print_stats"].state = "printing"
    plug(bus, A, devnum=40)
    look(m, reactor, 60)
    assert m.ace_devices == []
    m.printer.objects["print_stats"].state = "complete"
    look(m, reactor, 5)
    assert len(m.ace_devices) == 1


def test_order_matches_what_a_restart_would_give(hp, reactor):
    # Remembered order: A first, B second. Startup only found B (A was flapping), so B
    # got gates 1-4. When A settles and nothing is loaded, A takes 1-4 and B moves to 5-8.
    m, bus = hp
    m.device_mapper.offsets = {A["device_id"]: 0, B["device_id"]: 4}
    boot_with(m, reactor, B, offset=0)
    plug(bus, B, devnum=20)
    plug(bus, A, devnum=40)
    look(m, reactor, 20)
    assert [(d["device_id"], d["gate_offset"], d["name"]) for d in m.ace_devices] == [
        (A["device_id"], 0, "ACE_1"), (B["device_id"], 4, "ACE_2")]
    assert m.total_gates == 8
    assert m.device_mapper.offsets == {A["device_id"]: 0, B["device_id"]: 4}
    inst, local = m.get_device_for_gate(5)
    assert inst is m.ace_devices[1]["instance"] and local == 1


def test_gates_stay_put_while_filament_is_loaded(hp, reactor):
    m, bus = hp
    m.device_mapper.offsets = {A["device_id"]: 0, B["device_id"]: 4}
    m.is_tool_loaded = lambda: True
    boot_with(m, reactor, B, offset=0)
    plug(bus, B, devnum=20)
    plug(bus, A, devnum=40)
    look(m, reactor, 20)
    assert [(d["device_id"], d["gate_offset"]) for d in m.ace_devices] == [(B["device_id"], 0), (A["device_id"], 4)]
    assert m.device_mapper.saved == 0, "the remembered order is left for the next restart"


def test_unit_that_gave_up_is_reconnected_when_back(hp, reactor, fake_serial):
    from ace.device.ace_device import AceDevice
    import ace_sim
    m, bus = hp
    inst = boot_with(m, reactor, B, offset=0)
    # It drops off and stays away long enough for the driver to give up
    ace_sim.FakeSerial.simulators.pop(B["port"])
    inst._serial_disconnect()
    inst.connect()
    reactor.advance(120)
    assert inst.gave_up and not inst._connected
    # Back, and steady
    fake_serial(B["port"])
    plug(bus, B, devnum=21)
    look(m, reactor, 20)
    reactor.advance(0.1)
    assert inst._connected and not inst.gave_up


def test_controller_grows_per_gate_state(ace):
    from ace.ace_controller import AceController
    ctl = AceController.__new__(AceController)

    class _DM:
        total_gates = 8
    ctl.device_manager = _DM()
    ctl.gate_feed_assist = [True, False, False, False]
    ctl._on_devices_changed()
    assert ctl.gate_feed_assist == [True, False, False, False, False, False, False, False]


def test_quick_scan_reads_sysfs_without_opening_anything(ace, tmp_path, monkeypatch):
    from ace.device.device_discovery import AceDeviceDiscovery

    def usb_tty(tty, location, vid, devnum):
        usb = tmp_path / "devices" / location.split(":")[0]
        interface = usb / location
        interface.mkdir(parents=True)
        (usb / "idVendor").write_text(vid + "\n")
        (usb / "devnum").write_text(f"{devnum}\n")
        cls = tmp_path / "class"
        cls.mkdir(exist_ok=True)
        (cls / tty).mkdir()
        (cls / tty / "device").symlink_to(interface)

    usb_tty("ttyACM0", "1-2:1.0", "1d50", 3)          # the printer's board
    usb_tty("ttyACM1", "3-1.3.3:1.0", "28e9", 95)     # an ACE
    usb_tty("ttyACM2", "3-1.1.3:1.0", "28e9", 90)     # another ACE
    monkeypatch.setattr(AceDeviceDiscovery, "find_by_path_for_device",
                        staticmethod(lambda tty: f"/dev/serial/by-path/x-{tty[-1]}"))
    units = AceDeviceDiscovery.quick_scan(str(tmp_path / "class"))
    assert [(u["usb_location"], u["devnum"], u["device_id"]) for u in units] == [
        ("3-1.3.3:1.0", 95, "hub_3_port_1_3_3_1_0"), ("3-1.1.3:1.0", 90, "hub_3_port_1_1_3_1_0")]
    assert units[0]["port"] == "/dev/serial/by-path/x-1"
