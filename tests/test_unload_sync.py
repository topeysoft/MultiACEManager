"""
Sensor clearing during unload: the ACE must pull *while* the extruder retracts
(started first, same speed, a little longer), never after it.
"""
import pytest


class Sensor:
    def __init__(self, clear_after):
        self.clear_after = clear_after      # number of extruder retracts until the sensor clears
        self.retracts = 0
        self.runout_helper = self

    @property
    def filament_present(self):
        return self.retracts < self.clear_after


class Recorder:
    """Records the interleaving of ACE and extruder actions."""
    def __init__(self):
        self.events = []


class FakeDevice:
    def __init__(self, rec):
        self.rec = rec
        self.device_id = "sim"

    def retract(self, gate, length, speed, callback):
        self.rec.events.append(("ace_retract", gate, length, speed))
        callback({"code": 0})

    def wait_ready(self, timeout=30.0):
        self.rec.events.append(("ace_wait",))

    def stop_feeding(self, gate, callback):
        self.rec.events.append(("ace_stop", gate))
        callback({"code": 0})


class FakeToolhead:
    def __init__(self, rec):
        self.rec = rec
        self.pos = [0.0, 0.0, 0.0, 0.0]

    def get_position(self):
        return list(self.pos)

    def move(self, pos, speed):
        delta = pos[3] - self.pos[3]
        self.pos = pos
        self.rec.events.append(("extruder_move", round(delta, 3), speed))

    def wait_moves(self):
        self.rec.events.append(("extruder_wait",))


class FakeGcode:
    def __init__(self):
        self.msgs = []
        self.scripts = []

    def respond_info(self, m):
        self.msgs.append(m)

    def run_script_from_command(self, s):
        self.scripts.append(s)


class FakeController:
    def __init__(self, rec, sensor):
        self.gcode = FakeGcode()
        self.device_manager = None
        self.save_variables = None
        self.reactor = type("R", (), {"monotonic": staticmethod(lambda: 0.0),
                                      "pause": staticmethod(lambda t: rec.events.append(("pause",)))})()
        self.toolhead = FakeToolhead(rec)
        self.extruder_sensor = sensor
        self.extruder_clearance_length = 60
        self.sensor_clear_max_distance = 20
        self.sensor_clear_speed = 20
        self.extruder_move_speed = 5
        self.retract_speed = 50
        self.error_macros = "_ACE_ON_SENSOR_ERROR"


@pytest.fixture
def make(ace):
    from ace.commands.tool_commands import ToolCommands

    def _make(clear_after):
        rec = Recorder()
        sensor = Sensor(clear_after)
        ctrl = FakeController(rec, sensor)
        tc = ToolCommands(ctrl)
        dev = FakeDevice(rec)
        # the fake sensor counts extruder retracts
        orig_move = ctrl.toolhead.move
        def move(pos, speed):
            orig_move(pos, speed)
            sensor.retracts += 1
        ctrl.toolhead.move = move
        return tc, dev, rec, ctrl

    return _make


def test_ace_pulls_before_and_during_extruder_retract(make):
    tc, dev, rec, ctrl = make(clear_after=1)
    tc._sequential_retract_to_clear_sensor(2, dev, 2)
    kinds = [e[0] for e in rec.events]
    # slack take-up first
    assert rec.events[0] == ("ace_retract", 2, 60, 20)
    assert kinds[:3] == ["ace_retract", "pause", "ace_wait"]
    # then, per attempt: ACE leads with an oversized pull, extruder follows, ACE stopped and waited on
    attempt = rec.events[3:]
    # 60mm + (60/5 s) * 25 mm/s + 20mm margin = 380mm, at the configured retract speed
    assert attempt[0] == ("ace_retract", 2, 380, 50), "ACE pull must outlast the extruder move"
    assert attempt[1] == ("pause",)
    assert attempt[2] == ("extruder_move", -60, 5)
    assert attempt[3] == ("extruder_wait",)
    assert attempt[4] == ("ace_stop", 2)
    assert attempt[5] == ("pause",)
    assert attempt[6] == ("ace_wait",)
    assert len(attempt) == 7, "sensor cleared after one attempt"
    assert any("Sensor cleared after 1" in m for m in ctrl.gcode.msgs)


def test_retries_then_raises_command_level_error(ace, make):
    from ace.exceptions import AceException
    tc, dev, rec, ctrl = make(clear_after=99)
    with pytest.raises(AceException, match="after 5 attempts"):
        tc._sequential_retract_to_clear_sensor(2, dev, 2)
    assert sum(1 for e in rec.events if e[0] == "extruder_move") == 5
    assert sum(1 for e in rec.events if e[0] == "ace_retract") == 6  # take-up + 5 attempts
    assert ctrl.gcode.scripts == ["_ACE_ON_SENSOR_ERROR TOOL=2 ERROR='EXTRUDER_SENSOR_NOT_CLEAR'"]
