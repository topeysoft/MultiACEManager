"""AceException raised inside a G-code handler must surface as a command error, never a Klipper shutdown."""
import pytest


class CommandError(Exception):
    pass


class FakeGcmd:
    error = CommandError


def test_guard_converts_ace_exception(ace):
    from ace.exceptions import AceException, gcode_guard

    def handler(gcmd):
        raise AceException("ACE Error: sensor not clear")

    with pytest.raises(CommandError, match="sensor not clear"):
        gcode_guard(handler)(FakeGcmd())


def test_guard_passes_other_exceptions_and_results(ace):
    from ace.exceptions import gcode_guard

    assert gcode_guard(lambda g: 42)(FakeGcmd()) == 42
    with pytest.raises(KeyError):
        gcode_guard(lambda g: {}["x"])(FakeGcmd())


def test_all_command_modules_register_through_guard(ace):
    import inspect
    from ace.commands import tool_commands, dryer_commands, config_commands, status_commands
    for mod in (tool_commands, dryer_commands, config_commands, status_commands):
        src = inspect.getsource(mod)
        bare = [line for line in src.splitlines() if "register_command(" in line or "self.cmd_" in line]
        unguarded = [l for l in bare if "self.cmd_" in l and "gcode_guard(" not in l and "def " not in l]
        assert not unguarded, f"{mod.__name__}: {unguarded}"
