"""Endless spool: carry on only with a spool of the same material AND colour."""
import pytest


class _SaveVariables:
    def __init__(self, **variables):
        self.allVariables = dict(variables)


class _DeviceManager:
    def __init__(self, slots):
        self.slots = slots
        self.total_gates = len(slots)
    def get_aggregated_status(self):
        return {'slots': self.slots}


def _slot(index, status='ready', type='', color=(0, 0, 0)):
    return {'index': index, 'status': status, 'sku': '', 'type': type,
            'color': list(color), 'rfid': 1}


def _controller(ace, slots, colors, types):
    from ace.ace_controller import AceController
    c = AceController.__new__(AceController)
    c.save_variables = _SaveVariables(ace_gate_color=list(colors), ace_gate_type=list(types))
    c.device_manager = _DeviceManager(slots)
    return c


def test_green_out_does_not_continue_in_blue_or_purple_petg(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1), _slot(2)],
                    ['00FF00', '0000FF', '800080'], ['PETG', 'PETG', 'PETG'])
    assert c._find_endless_replacement(0) is None


def test_two_white_pla_match_each_other(ace):
    c = _controller(ace, [_slot(0), _slot(1, 'empty'), _slot(2), _slot(3)],
                    ['000000', 'FFFFFF', '00FF00', '#ffffff'], ['PLA', 'PLA', 'PLA', 'PLA'])
    assert c._find_endless_replacement(1) == 3


def test_rfid_tag_colour_overrides_saved_colour(ace):
    # Saved says gate 1 is white, but its tag says red: no match for white gate 0.
    c = _controller(ace, [_slot(0, 'empty'), _slot(1, type='PLA', color=(255, 0, 0)), _slot(2)],
                    ['FFFFFF', 'FFFFFF', 'FFFFFF'], ['PLA', 'PLA', 'PLA'])
    assert c._find_endless_replacement(0) == 2
    # And a tag can make a match the saved colour would not.
    c = _controller(ace, [_slot(0, 'empty'), _slot(1, type='PLA', color=(250, 250, 250))],
                    ['FFFFFF', '000000'], ['PLA', 'PETG'])
    assert c._find_endless_replacement(0) == 1


def test_unknown_colour_never_matches(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1)], ['', 'FFFFFF'], ['PLA', 'PLA'])
    assert c._find_endless_replacement(0) is None
    c = _controller(ace, [_slot(0, 'empty'), _slot(1)], ['FFFFFF', 'nope'], ['PLA', 'PLA'])
    assert c._find_endless_replacement(0) is None
    c = _controller(ace, [_slot(0, 'empty'), _slot(1)], ['FFFFFF'], ['PLA', 'PLA'])
    assert c._find_endless_replacement(0) is None


def test_material_case_and_whitespace_ignored(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1)], ['FFFFFF', 'FFFFFF'], ['petg ', ' PETG'])
    assert c._find_endless_replacement(0) == 1


def test_different_material_same_colour_does_not_match(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1)], ['FFFFFF', 'FFFFFF'], ['PLA', 'PETG'])
    assert c._find_endless_replacement(0) is None


def test_empty_slots_are_skipped(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1, 'empty')], ['FFFFFF', 'FFFFFF'], ['PLA', 'PLA'])
    assert c._find_endless_replacement(0) is None


def test_closest_colour_wins_ties_lowest_index(ace):
    c = _controller(ace, [_slot(0, 'empty'), _slot(1), _slot(2), _slot(3)],
                    ['FF0000', 'D20000', 'F00000', 'F00000'], ['ABS'] * 4)
    assert c._find_endless_replacement(0) == 2


class _Gcode:
    def __init__(self):
        self.scripts, self.said = [], []
    def run_script_from_command(self, script):
        self.scripts.append(script)
    def respond_info(self, msg):
        self.said.append(msg)


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _runout(ace, slots, colors, types):
    c = _controller(ace, slots, colors, types)
    c.save_variables.allVariables.update(ace_current_index=0, ace_endless_spool=True)
    c.save_variable = lambda name, value, write=False: None
    c.gcode = _Gcode()
    c.reactor = _Obj(monotonic=lambda: 0.0)
    pause = _Obj(pauses=[], resumes=[])
    pause.send_pause_command = lambda: pause.pauses.append(1)
    pause.send_resume_command = lambda: pause.resumes.append(1)
    objects = {'print_stats': _Obj(get_status=lambda now: {'state': 'printing'}),
               'pause_resume': pause}
    c.printer = _Obj(lookup_object=lambda name, default=None: objects.get(name, default))
    device = _Obj(get_status=lambda: {'active_gate': [s['status'] for s in slots]})
    c.device_manager.get_device_for_gate = lambda gate: (device, gate)
    c._extruder_sensor_handler(0.0, False, None)
    return c, pause


def test_runout_switches_to_matching_spool(ace):
    c, pause = _runout(ace, [_slot(0, 'empty'), _slot(1), _slot(2)],
                       ['00FF00', '0000FF', '00FF00'], ['PETG'] * 3)
    assert c.gcode.said == ['Endless spool: T0 empty, switching to T2']
    assert c.gcode.scripts == ['ACE_CHANGE_TOOL TOOL=2']
    assert pause.resumes == [1]


def test_runout_without_match_stays_paused(ace):
    c, pause = _runout(ace, [_slot(0, 'empty'), _slot(1), _slot(2)],
                       ['00FF00', '0000FF', '800080'], ['PETG'] * 3)
    assert c.gcode.said == ['Filament runout on T0! No matching spools available '
                            '(material: PETG, colour: #00FF00)']
    assert c.gcode.scripts == []
    assert pause.pauses == [1] and pause.resumes == []
