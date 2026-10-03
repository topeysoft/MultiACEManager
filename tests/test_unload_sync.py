"""
Sensor clearing during unload: the ACE must pull *while* the extruder retracts
(started first, same speed, a little longer), never after it, and it must stop
as soon as the extruder sensor clears. Once the tip is past the sensor it's out
of the gears, and every millimetre the ACE pulls after that comes on top of
toolchange_retract_length (the pull back past the splitter).
"""
import pytest


class Clock:
    """Reactor stand-in with a clock that only moves when something waits."""
    def __init__(self, rec):
        self.t = 0.0
        self.rec = rec

    def monotonic(self):
        return self.t

    def pause(self, until):
        self.rec.events.append(("pause",))
        self.t = max(self.t, until)


class Sensor:
    """Filament present until the extruder has pulled the tip `clear_at` mm back."""
    def __init__(self, toolhead, clear_at):
        self.toolhead = toolhead
        self.clear_at = clear_at
        self.runout_helper = self

    @property
    def filament_present(self):
        return self.toolhead.retracted() < self.clear_at


class Recorder:
    """Records the interleaving of ACE and extruder actions, with the clock."""
    def __init__(self):
        self.events = []


class FakeDevice:
    def __init__(self, rec, clock):
        self.rec = rec
        self.clock = clock
        self.device_id = "sim"

    def retract(self, gate, length, speed, callback):
        self.rec.events.append(("ace_retract", gate, length, speed))
        callback({"code": 0})

    def wait_ready(self, timeout=30.0):
        self.rec.events.append(("ace_wait",))

    def stop_feeding(self, gate, callback):
        self.rec.events.append(("ace_stop", gate, round(self.clock.t, 2)))
        callback({"code": 0})


class FakeToolhead:
    """Extruder moves take length/speed seconds of the fake clock, starting when queued."""
    def __init__(self, rec, clock):
        self.rec = rec
        self.clock = clock
        self.pos = [0.0, 0.0, 0.0, 0.0]
        self.done_before = 0.0     # mm retracted by finished moves
        self.move_start = 0.0
        self.move_len = 0.0
        self.move_speed = 1.0

    def retracted(self):
        running = min(self.move_len, max(0.0, self.clock.t - self.move_start) * self.move_speed)
        return self.done_before + running

    def get_position(self):
        return list(self.pos)

    def move(self, pos, speed):
        delta = pos[3] - self.pos[3]
        self.pos = pos
        self.done_before = self.retracted()
        self.move_start, self.move_len, self.move_speed = self.clock.t, max(0.0, -delta), speed
        self.rec.events.append(("extruder_move", round(delta, 3), speed))

    def wait_moves(self):
        self.clock.t = max(self.clock.t, self.move_start + self.move_len / self.move_speed)
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
    def __init__(self, rec, clock, clear_at):
        self.gcode = FakeGcode()
        self.device_manager = None
        self.save_variables = None
        self.reactor = clock
        self.toolhead = FakeToolhead(rec, clock)
        self.extruder_sensor = Sensor(self.toolhead, clear_at)
        self.extruder_clearance_length = 60
        self.sensor_clear_max_distance = 20
        self.sensor_clear_speed = 20
        self.extruder_move_speed = 5
        self.retract_speed = 50
        self.error_macros = "_ACE_ON_SENSOR_ERROR"


@pytest.fixture
def make(ace):
    from ace.commands.tool_commands import ToolCommands

    def _make(clear_at):
        rec = Recorder()
        clock = Clock(rec)
        ctrl = FakeController(rec, clock, clear_at)
        tc = ToolCommands(ctrl)
        dev = FakeDevice(rec, clock)
        return tc, dev, rec, ctrl

    return _make


def without_pauses(events):
    return [e for e in events if e[0] != "pause"]


def test_ace_pulls_before_and_during_extruder_retract(make):
    tc, dev, rec, ctrl = make(clear_at=30)
    tc._sequential_retract_to_clear_sensor(2, dev, 2)
    ev = without_pauses(rec.events)
    # slack take-up first
    assert ev[0] == ("ace_retract", 2, 60, 20)
    assert ev[1] == ("ace_wait",)
    # then the ACE leads with an oversized pull and the extruder follows:
    # 60mm + (60/5 s) * 25 mm/s + 20mm margin = 380mm, at the configured retract speed
    assert ev[2] == ("ace_retract", 2, 380, 50), "ACE pull must outlast the extruder move"
    assert ev[3] == ("extruder_move", -60, 5)
    # the ACE is stopped as the sensor clears, before the extruder move is over
    assert ev[4][0] == "ace_stop" and ev[5] == ("extruder_wait",)
    assert ev[6] == ("ace_wait",)
    assert len(ev) == 7, "sensor cleared after one attempt"
    assert any("Sensor cleared after 1" in m for m in ctrl.gcode.msgs)


def test_ace_stops_when_the_sensor_clears_not_when_the_extruder_finishes(make):
    tc, dev, rec, ctrl = make(clear_at=30)
    tc._sequential_retract_to_clear_sensor(2, dev, 2)
    move_at = 1.0 + 0.5                         # take-up pause, then the ACE's head start
    stop = next(e for e in rec.events if e[0] == "ace_stop")
    # 30mm at 5mm/s is 6s into a 12s move; stopped within one sensor poll of that
    assert move_at + 6.0 <= stop[2] <= move_at + 6.0 + tc.SENSOR_POLL_INTERVAL + 1e-9
    # the old way stopped at the end of the move: 6s more of free pulling at up to 25mm/s
    assert stop[2] < move_at + 12.0


def test_sensor_that_clears_on_the_second_attempt(make):
    tc, dev, rec, ctrl = make(clear_at=90)
    tc._sequential_retract_to_clear_sensor(2, dev, 2)
    ev = without_pauses(rec.events)
    assert sum(1 for e in ev if e[0] == "extruder_move") == 2
    stops = [e for e in ev if e[0] == "ace_stop"]
    assert len(stops) == 2
    # the first attempt watched its whole move (plus the start-up slack); the second stopped
    # 30mm (6s) into it
    first_end = 1.5 + 12.0 + tc.MOVE_START_SLACK
    second_move_at = first_end + 0.5 + 0.5      # settle after the stop, then the ACE's head start
    assert stops[0][2] == pytest.approx(first_end, abs=0.01)
    assert second_move_at + 6.0 <= stops[1][2] <= second_move_at + 6.0 + tc.SENSOR_POLL_INTERVAL + 1e-9
    assert any("Sensor cleared after 2" in m for m in ctrl.gcode.msgs)


def test_retries_then_raises_command_level_error(ace, make):
    from ace.exceptions import AceException
    tc, dev, rec, ctrl = make(clear_at=10_000)
    with pytest.raises(AceException, match="after 5 attempts"):
        tc._sequential_retract_to_clear_sensor(2, dev, 2)
    assert sum(1 for e in rec.events if e[0] == "extruder_move") == 5
    assert sum(1 for e in rec.events if e[0] == "ace_retract") == 6  # take-up + 5 attempts
    assert ctrl.gcode.scripts == ["_ACE_ON_SENSOR_ERROR TOOL=2 ERROR='EXTRUDER_SENSOR_NOT_CLEAR'"]
