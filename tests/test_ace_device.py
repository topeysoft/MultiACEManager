"""
AceDevice driver against the in-process simulator.

The driver has no timers of its own: DeviceManager calls ``process_io`` on a
global timer. ``pump`` plays that role here, one poll at a time.
"""
import pytest

PORT = "/dev/ttyACE0"


@pytest.fixture
def make_device(ace, reactor, fake_serial):
    from ace.device.ace_device import AceDevice

    def _make(port=PORT, register=True, **sim_kwargs):
        sim = fake_serial(port, **sim_kwargs) if register else None
        device = AceDevice(port=port, baud=115200, device_id="sim0", reactor=reactor,
                           connect_retry_delay=0.5, connect_retry_max=3)
        return device, sim

    return _make


def pump(device, reactor, polls=1, interval=0.5):
    """Run ``polls`` I/O cycles the way DeviceManager's global timer would."""
    for _ in range(polls):
        device.process_io(reactor.monotonic())
        reactor.advance(interval)


def connect(device, reactor):
    device.connect()
    reactor.advance(0.1)  # fires the connect timer registered at NOW
    assert device._connected, "device should connect on first attempt"


def test_connect_sends_get_info_then_polls_status(make_device, reactor):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=3)
    methods = [r["method"] for r in sim.received]
    assert methods[0] == "get_info"
    assert "get_status" in methods[1:]
    assert device.is_ready()


def test_status_poll_updates_gate_state(make_device, reactor):
    device, sim = make_device()
    sim.load_slot(2, sku="AHPEGY-101", material="PETG", color=(117, 120, 123))
    connect(device, reactor)
    pump(device, reactor, polls=3)
    assert device.gate_status == ["empty", "empty", "ready", "empty"]
    assert device.get_status()["slots"][2]["type"] == "PETG"


def test_missing_device_retries_then_gives_up(make_device, reactor):
    device, _ = make_device(register=False)
    device.connect()
    reactor.advance(60)
    assert device._connected is False
    assert device._connection_retry_count == 3
    assert reactor.pending_timers == [], "retry timer must stop after max attempts"


def test_feed_is_sent_with_params_and_callback_runs(make_device, reactor):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    responses = []
    device.feed(gate=1, length=100, speed=50, callback=responses.append)
    pump(device, reactor, polls=2)
    feeds = sim.requests("feed_filament")
    assert feeds and feeds[0]["params"] == {"index": 1, "length": 100, "speed": 50}
    assert responses and responses[0]["code"] == 0
    assert sim.status == "busy"
    pump(device, reactor, polls=sim.busy_polls + 1)
    assert device.is_ready()


def test_retract_uses_unwind_method(make_device, reactor):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    device.retract(gate=3, length=170, speed=50, callback=lambda r: None)
    pump(device, reactor, polls=2)
    assert sim.requests("unwind_filament")[0]["params"] == {"index": 3, "length": 170, "speed": 50}


def test_dryer_start_and_stop(make_device, reactor):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    device.start_dryer(temp=55, duration=240, callback=lambda r: None)
    pump(device, reactor, polls=2)
    assert sim.dryer["status"] == "drying" and sim.dryer["target_temp"] == 55
    device.stop_dryer(callback=lambda r: None)
    pump(device, reactor, polls=2)
    assert sim.dryer["status"] == "stop"


@pytest.mark.parametrize("call", [
    lambda d: d.feed(4, 10, 10, lambda r: None),
    lambda d: d.retract(-1, 10, 10, lambda r: None),
    lambda d: d.start_feed_assist(4, lambda r: None),
    lambda d: d.stop_feed_assist(4, lambda r: None),
    lambda d: d.stop_feeding(9, lambda r: None),
    lambda d: d.update_feeding_speed(4, 10, lambda r: None),
])
def test_invalid_gate_raises_ace_exception(ace, make_device, reactor, call):
    device, _ = make_device()
    connect(device, reactor)
    with pytest.raises(ace.AceException):
        call(device)


def test_dropped_response_times_out_and_recovers(make_device, reactor, caplog):
    from ace.protocol.constants import REQUEST_TIMEOUT
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    sim.drop_next_response = True
    device.feed(0, 10, 10, callback=lambda r: None)
    pump(device, reactor, polls=1)
    assert device.lock is True, "waiting on a response"
    reactor.advance(REQUEST_TIMEOUT + 0.1)
    pump(device, reactor, polls=1)
    assert "Request timeout" in caplog.text
    pump(device, reactor, polls=3)
    assert device._connected and device.is_ready()


def test_corrupt_response_is_logged_and_skipped(make_device, reactor, caplog):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    sim.corrupt_next_crc = True
    pump(device, reactor, polls=2)
    assert "CRC mismatch" in caplog.text
    assert device._connected


def test_write_io_error_disconnects_and_reconnects(make_device, reactor, caplog):
    device, sim = make_device()
    connect(device, reactor)
    pump(device, reactor, polls=2)
    first_serial = device._serial
    sim.fail_next_writes = 3  # exhaust the driver's 3 write retries
    pump(device, reactor, polls=1)
    assert "Write failed after 3 attempts" in caplog.text
    assert not first_serial.is_open
    reactor.advance(1.0)  # reconnect timer
    assert device._connected
    assert device._serial is not first_serial
    pump(device, reactor, polls=3)  # get_info, then a status poll and its reply
    assert device.is_ready()
