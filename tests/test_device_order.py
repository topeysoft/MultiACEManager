"""Gate-order rules: config device_order, remembered offsets, then USB location."""
import pytest


@pytest.fixture
def order(ace):
    from ace.device.device_manager import order_devices
    return order_devices


def dev(device_id, location):
    return {"device_id": device_id, "usb_location": location}


A, B, C = dev("hub_3_port_1_1_3", "3-1.1.3"), dev("hub_3_port_1_3_3", "3-1.3.3"), dev("hub_3_port_1_2_3", "3-1.2.3")


def ids(devices):
    return [d["device_id"] for d in devices]


def test_unknown_devices_sort_by_usb_location(order):
    assert ids(order([B, C, A])) == [A["device_id"], C["device_id"], B["device_id"]]


def test_remembered_offsets_beat_usb_location(order):
    # B was gates 0-3 last time even though A has the lower port: keep B first.
    known = {A["device_id"]: 4, B["device_id"]: 0}
    assert ids(order([A, B], known)) == [B["device_id"], A["device_id"]]


def test_new_device_goes_after_remembered_ones(order):
    known = {A["device_id"]: 4, B["device_id"]: 0}
    # C is new and has the lowest port; it must not steal gates 0-3.
    assert ids(order([C, A, B], known)) == [B["device_id"], A["device_id"], C["device_id"]]


def test_equal_remembered_offsets_fall_back_to_usb_location(order):
    known = {A["device_id"]: 0, C["device_id"]: 0}
    assert ids(order([C, A], known)) == [A["device_id"], C["device_id"]]


def test_config_device_order_wins_and_resolves_aliases(order):
    known = {A["device_id"]: 0, B["device_id"]: 4}
    aliases = {"right": B["device_id"]}
    assert ids(order([A, B], known, device_order=["right"], aliases=aliases)) == [B["device_id"], A["device_id"]]
    assert ids(order([A, B, C], known, device_order=[C["device_id"], "right"], aliases=aliases)) == \
        [C["device_id"], B["device_id"], A["device_id"]]


def test_mapper_persists_gate_offsets_for_ordering(ace, tmp_path):
    from ace.device.device_mapper import AceDeviceMapper
    path = tmp_path / "ace_device_map.cfg"
    m = AceDeviceMapper(str(path))
    m.update_device(A["device_id"], "/dev/serial/by-path/a", A["usb_location"], 4)
    m.update_device(B["device_id"], "/dev/serial/by-path/b", B["usb_location"], 0)
    m.set_alias(B["device_id"], "right")
    m.save()

    reloaded = AceDeviceMapper(str(path))
    offsets = {d: i["last_gate_offset"] for d, i in reloaded.get_all_devices().items()}
    assert offsets == {A["device_id"]: 4, B["device_id"]: 0}
    assert reloaded.get_all_aliases() == {"right": B["device_id"]}


class _Mapper:
    """Minimal stand-in for AceDeviceMapper used by set_device_order."""
    def __init__(self):
        self.saved = 0
        self.offsets = {}
        self.aliases = {}
    def get_all_devices(self):
        return {d: {"last_gate_offset": o} for d, o in self.offsets.items()}
    def get_all_aliases(self):
        return dict(self.aliases)
    def resolve_device_id(self, ref):
        return self.aliases.get(ref) or (ref if ref in self.offsets else None)
    def get_alias(self, device_id):
        return next((a for a, d in self.aliases.items() if d == device_id), "")
    def update_device(self, device_id, port, usb_location=None, current_gate_offset=None, port_tty=None):
        self.offsets[device_id] = current_gate_offset
    def save(self):
        self.saved += 1


@pytest.fixture
def manager(ace):
    from ace.device.device_manager import AceDeviceManager
    m = AceDeviceManager.__new__(AceDeviceManager)  # skip __init__ (needs Klipper config/discovery)
    m.device_mapper = _Mapper()
    m.device_order = []
    m.ace_devices = [
        {"name": "ACE_1", "device_id": A["device_id"], "port": "/a", "usb_location": A["usb_location"], "gate_offset": 0, "instance": object()},
        {"name": "ACE_2", "device_id": B["device_id"], "port": "/b", "usb_location": B["usb_location"], "gate_offset": 4, "instance": object()},
    ]
    m.device_mapper.offsets = {A["device_id"]: 0, B["device_id"]: 4}
    m.device_mapper.aliases = {"right": B["device_id"]}
    m.total_gates = 8
    return m


def test_set_device_order_swaps_and_persists(manager):
    changes = manager.set_device_order(["ACE_2", "ACE_1"])
    assert [c[1:] for c in changes] == [(B["device_id"], 4, 0), (A["device_id"], 0, 4)]
    assert [d["name"] for d in manager.ace_devices] == ["ACE_1", "ACE_2"]
    assert manager.ace_devices[0]["device_id"] == B["device_id"] and manager.ace_devices[0]["gate_offset"] == 0
    assert manager.device_mapper.offsets == {A["device_id"]: 4, B["device_id"]: 0}
    assert manager.device_mapper.saved == 1
    # Routing follows the new offsets
    inst, local = manager.get_device_for_gate(1)
    assert inst is manager.ace_devices[0]["instance"] and local == 1


def test_set_device_order_accepts_alias_index_and_partial_list(manager):
    manager.set_device_order(["right"])
    assert manager.ace_devices[0]["device_id"] == B["device_id"]
    manager.set_device_order(["2"])  # 1-based index of the (now second) device A
    assert manager.ace_devices[0]["device_id"] == A["device_id"]


def test_set_device_order_rejects_unknown_and_duplicates(manager):
    with pytest.raises(ValueError):
        manager.set_device_order(["nope"])
    with pytest.raises(ValueError):
        manager.set_device_order(["ACE_1", "ACE_1"])
