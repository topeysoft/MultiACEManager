"""ACE_CHANGE_TOOL PURGE=0: load without running the purge (poop) macro."""
import pytest


class _Gcode:
    def __init__(self):
        self.scripts, self.said = [], []
    def run_script_from_command(self, script):
        self.scripts.append(script)
    def respond_info(self, msg):
        self.said.append(msg)


class _Controller:
    poop_macros = "_POOP"
    toolhead_sensor = None


@pytest.fixture
def tools(ace):
    from ace.commands.tool_commands import ToolCommands
    t = ToolCommands.__new__(ToolCommands)
    t.gcode = _Gcode()
    t.controller = _Controller()
    t._feed_to_extruder = lambda tool: None
    t._ensure_temperature = lambda tool, skip_preheat=False: None
    t._feed_extruder_to_nozzle = lambda: None
    return t


def test_load_purges_by_default(tools):
    tools._load_tool(2)
    assert tools.gcode.scripts == ["_POOP"]


def test_purge_0_skips_the_macro(tools):
    tools._load_tool(2, purge=False)
    assert tools.gcode.scripts == []
    assert "ACE: Same colour, skipping purge" in tools.gcode.said
    assert tools.gcode.said[-1] == "ACE: Load complete"
