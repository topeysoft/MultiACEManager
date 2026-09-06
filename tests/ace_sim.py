"""
ACE Pro device simulator.

Two ways to use it:

1. In-process (unit tests): ``FakeSerial`` replaces ``serial.Serial`` and routes
   every packet written by the driver to an ``AceSimulator`` registered for that
   port path. No threads, no sleeping, fully deterministic.

2. As a pseudo-terminal server (integration): ``python tests/ace_sim.py -n 2``
   creates two pty devices that speak the ACE protocol. Point a real Klipper at
   them with ``serial_ports: /dev/ttys00X, /dev/ttys00Y`` in ``[ace]``.

The protocol is the one implemented in ``extras/protocol``: a JSON-RPC style
request/response over framed packets. Methods mirror what ``AceDevice`` sends.
"""
import argparse
import importlib.util
import os
import pathlib
import select
import struct
import sys
import time

EXTRAS_DIR = pathlib.Path(__file__).resolve().parents[1] / "extras"


def load_ace_package():
    """Import ``extras/`` as the package ``ace`` (its name on the printer)."""
    if "ace" in sys.modules:
        return sys.modules["ace"]
    spec = importlib.util.spec_from_file_location(
        "ace", EXTRAS_DIR / "__init__.py", submodule_search_locations=[str(EXTRAS_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ace"] = module
    spec.loader.exec_module(module)
    return module


def _protocol():
    load_ace_package()
    from ace.protocol.packet import AcePacket, calc_crc  # noqa: WPS433
    from ace.protocol import constants  # noqa: WPS433
    return AcePacket, calc_crc, constants


class AceSimulator:
    """
    Behavioural model of one ACE Pro unit.

    ``handle(request) -> response`` is the whole device. State that tests care
    about is plain attributes so they can be inspected or preset.
    """

    def __init__(self, num_slots=4, model="ACE Pro", firmware="sim-1.0", temp=28,
                 busy_polls=2):
        self.model = model
        self.firmware = firmware
        self.temp = temp
        self.status = "ready"
        self.fan_speed = 7000
        self.enable_rfid = 1
        self.feed_assist_count = 0
        self.cont_assist_time = 0.0
        self.dryer = {"status": "stop", "target_temp": 0, "duration": 0, "remain_time": 0}
        self.slots = [
            {"index": i, "status": "empty", "sku": "", "type": "", "color": [0, 0, 0], "rfid": 1}
            for i in range(num_slots)
        ]
        self.feed_assist = [False] * num_slots
        # A feed/retract keeps the unit "busy" for this many get_status polls.
        self.busy_polls = busy_polls
        self._busy_remaining = 0
        # Fault injection knobs (each applies to the next matching event only).
        self.drop_next_response = False
        self.corrupt_next_crc = False
        self.fail_next_writes = 0
        # Everything received, in order, for assertions.
        self.received = []

    # --- helpers for tests --------------------------------------------------
    def load_slot(self, index, sku="SIM-PLA", material="PLA", color=(255, 0, 0)):
        slot = self.slots[index]
        slot.update(status="ready", sku=sku, type=material, color=list(color))

    def empty_slot(self, index):
        self.slots[index].update(status="empty", sku="", type="", color=[0, 0, 0])

    def requests(self, method=None):
        return [r for r in self.received if method is None or r.get("method") == method]

    # --- protocol -----------------------------------------------------------
    def handle(self, request):
        self.received.append(request)
        rid = request.get("id")
        method = request.get("method")
        params = request.get("params", {}) or {}
        handler = getattr(self, f"_m_{method}", None)
        if handler is None:
            return {"id": rid, "code": 1, "msg": f"unknown method {method}"}
        result = handler(params)
        return {"id": rid, "code": 0, "result": result}

    def _m_get_info(self, params):
        return {"id": 1, "slots": len(self.slots), "model": self.model, "firmware": self.firmware}

    def _m_get_status(self, params):
        if self._busy_remaining > 0:
            self._busy_remaining -= 1
            if self._busy_remaining == 0:
                self.status = "ready"
        return {
            "status": self.status,
            "temp": self.temp,
            "enable_rfid": self.enable_rfid,
            "fan_speed": self.fan_speed,
            "feed_assist_count": self.feed_assist_count,
            "cont_assist_time": self.cont_assist_time,
            "dryer_status": dict(self.dryer),
            "slots": [dict(s) for s in self.slots],
        }

    def _start_busy(self):
        self.status = "busy"
        self._busy_remaining = self.busy_polls

    def _m_feed_filament(self, params):
        self._start_busy()
        return {"index": params.get("index"), "length": params.get("length"), "speed": params.get("speed")}

    def _m_unwind_filament(self, params):
        self._start_busy()
        return {"index": params.get("index"), "length": params.get("length"), "speed": params.get("speed")}

    def _m_stop_feed_filament(self, params):
        self.status = "ready"
        self._busy_remaining = 0
        return {}

    def _m_update_feeding_speed(self, params):
        return {"index": params.get("index"), "speed": params.get("speed")}

    def _m_start_feed_assist(self, params):
        self.feed_assist[params["index"]] = True
        self.feed_assist_count += 1
        return {}

    def _m_stop_feed_assist(self, params):
        self.feed_assist[params["index"]] = False
        return {}

    def _m_drying(self, params):
        self.dryer = {
            "status": "drying",
            "target_temp": params.get("temp", 0),
            "duration": params.get("duration", 0),
            "remain_time": params.get("duration", 0),
        }
        self.fan_speed = params.get("fan_speed", self.fan_speed)
        return {}

    def _m_drying_stop(self, params):
        self.dryer = {"status": "stop", "target_temp": 0, "duration": 0, "remain_time": 0}
        return {}


class PacketStream:
    """Turns a byte stream into decoded requests and encodes replies."""

    def __init__(self, simulator):
        self.sim = simulator
        self.buffer = bytearray()
        self.AcePacket, self.calc_crc, self.constants = _protocol()

    def feed_bytes(self, data):
        """Consume raw bytes, return the encoded responses to send back."""
        self.buffer += data
        out = bytearray()
        head = self.constants.PROTOCOL_HEAD_BYTES
        while True:
            start = self.buffer.find(head)
            if start < 0:
                self.buffer.clear()
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 4:
                break
            payload_len = struct.unpack("<H", self.buffer[2:4])[0]
            total = 4 + payload_len + 2 + 1
            if len(self.buffer) < total:
                break
            packet = bytes(self.buffer[:total])
            del self.buffer[:total]
            request, error = self.AcePacket.decode(packet)
            if error:
                continue
            response = self.sim.handle(request)
            if self.sim.drop_next_response:
                self.sim.drop_next_response = False
                continue
            encoded = self.AcePacket.encode(response)
            if self.sim.corrupt_next_crc:
                self.sim.corrupt_next_crc = False
                encoded = encoded[:-3] + bytes([encoded[-3] ^ 0xFF]) + encoded[-2:]
            out += encoded
        return bytes(out)


class FakeSerial:
    """
    Drop-in for ``serial.Serial`` backed by an ``AceSimulator``.

    ``FakeSerial.simulators`` maps port path -> simulator. Opening any other
    port raises ``serial.SerialException`` exactly like a missing device.
    """

    simulators = {}
    instances = []

    def __init__(self, port=None, baudrate=115200, **kwargs):
        import serial as pyserial
        if port not in self.simulators:
            raise pyserial.SerialException(
                f"[Errno 2] could not open port {port}: No such file or directory")
        self.port = port
        self.baudrate = baudrate
        self.kwargs = kwargs
        self.sim = self.simulators[port]
        self.stream = PacketStream(self.sim)
        self.rx = bytearray()
        self.is_open = True
        self.written = []
        FakeSerial.instances.append(self)

    @property
    def in_waiting(self):
        self._require_open()
        return len(self.rx)

    def read(self, size=1):
        self._require_open()
        data = bytes(self.rx[:size])
        del self.rx[:size]
        return data

    def write(self, data):
        self._require_open()
        if self.sim.fail_next_writes > 0:
            self.sim.fail_next_writes -= 1
            raise OSError(5, "Input/output error")
        self.written.append(bytes(data))
        self.rx += self.stream.feed_bytes(bytes(data))
        return len(data)

    def close(self):
        self.is_open = False

    def _require_open(self):
        if not self.is_open:
            raise OSError(9, "Bad file descriptor")


# --- pty server -------------------------------------------------------------

def serve_ptys(count, verbose=False):
    """Expose ``count`` simulated units as pseudo-terminals until interrupted."""
    import pty
    import termios
    import tty

    units = []
    for i in range(count):
        master, slave = pty.openpty()
        tty.setraw(master)
        tty.setraw(slave)
        sim = AceSimulator(firmware=f"sim-1.0-{i}")
        sim.load_slot(0)
        units.append((master, os.ttyname(slave), sim, PacketStream(sim)))
        print(f"ACE_{i + 1}: {os.ttyname(slave)}", flush=True)
    print("serial_ports: " + ", ".join(u[1] for u in units), flush=True)
    print("Ctrl+C to stop", flush=True)
    fds = {u[0]: u for u in units}
    try:
        while True:
            readable, _, _ = select.select(list(fds), [], [], 1.0)
            for fd in readable:
                master, name, sim, stream = fds[fd]
                try:
                    data = os.read(master, 4096)
                except OSError:
                    continue
                if not data:
                    continue
                reply = stream.feed_bytes(data)
                if verbose and sim.received:
                    print(f"{name}: {sim.received[-1]}", flush=True)
                if reply:
                    os.write(master, reply)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ACE Pro protocol simulator over pty")
    parser.add_argument("-n", "--devices", type=int, default=1, help="number of simulated units")
    parser.add_argument("-v", "--verbose", action="store_true", help="print each request")
    args = parser.parse_args()
    serve_ptys(args.devices, args.verbose)
