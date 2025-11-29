"""
Tool-related G-code commands for ACE Pro system.

Commands:
- ACE_CHANGE_TOOL - Change to specified tool
- ACE_FEED - Feed filament from gate
- ACE_RETRACT - Retract filament to gate
"""

import logging


class ToolCommands:
    """
    Tool movement and change commands.

    This class contains all G-code commands related to tool changes
    and filament movement (feed/retract).
    """

    def __init__(self, controller):
        """
        Initialize tool commands.

        Args:
            controller: AceController instance
        """
        self.controller = controller
        self.gcode = controller.gcode
        self.device_manager = controller.device_manager
        self.save_variables = controller.save_variables
        self.reactor = controller.reactor

    def register(self):
        """Register all tool-related commands"""
        self.gcode.register_command(
            'ACE_CHANGE_TOOL', self.cmd_ACE_CHANGE_TOOL,
            desc='Change to specified tool')

        self.gcode.register_command(
            'ACE_FEED', self.cmd_ACE_FEED,
            desc='Feed filament from gate')

        self.gcode.register_command(
            'ACE_RETRACT', self.cmd_ACE_RETRACT,
            desc='Retract filament to gate')

        logging.info("ToolCommands: Registered ACE_CHANGE_TOOL, ACE_FEED, ACE_RETRACT")

    def cmd_ACE_CHANGE_TOOL(self, gcmd):
        """
        ACE_CHANGE_TOOL TOOL=<n>

        Change to specified tool (gate).
        Use TOOL=-1 to unload.
        """
        tool = gcmd.get_int('TOOL')

        if tool < -1 or tool >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid tool (valid: -1 or 0-{self.device_manager.total_gates-1})')

        was = self.controller.current_tool

        if was == tool:
            self.gcode.respond_info(f'ACE: Already on tool {tool}')
            return

        logging.info(f'ToolCommands: Tool change {was} => {tool}')
        self.gcode.respond_info(f'ACE: Tool change {was} => {tool}')

        # TODO: Implement full tool change sequence
        # This is a simplified version - full implementation would include:
        # - Unload from current tool (if was >= 0)
        #   - Retract to toolhead sensor
        #   - Execute cut/poop macros
        #   - Retract to gate
        #   - Park filament
        # - Load to new tool (if tool >= 0)
        #   - Feed from gate
        #   - Home to toolhead sensor
        #   - Feed to nozzle
        #   - Prime/purge

        if tool == -1:
            # Unload sequence
            if was >= 0:
                self._unload_tool(was)
            else:
                self.gcode.respond_info('ACE: No tool loaded, nothing to unload')
        else:
            # Full tool change sequence
            if was >= 0:
                self._unload_tool(was)
            self._load_tool(tool)

        # Update current tool
        self.controller.current_tool = tool
        self.controller.save_variable('ace_current_index', tool, True)

    def _unload_tool(self, tool):
        """
        Unload filament from specified tool.

        Args:
            tool: Tool (gate) number to unload
        """
        self.gcode.respond_info(f'ACE: Unloading tool {tool}...')

        # TODO: Implement full unload sequence
        # 1. Check toolhead sensor state
        # 2. Retract to toolhead sensor if present
        # 3. Execute cut/poop macros if configured
        # 4. Retract to extruder sensor
        # 5. Retract to gate
        # 6. Park filament in gate

        logging.info(f'ToolCommands: Unload tool {tool} (not yet fully implemented)')
        self.gcode.respond_info('ACE: Unload sequence (simplified)')

    def _load_tool(self, tool):
        """
        Load filament for specified tool.

        Args:
            tool: Tool (gate) number to load
        """
        self.gcode.respond_info(f'ACE: Loading tool {tool}...')

        # TODO: Implement full load sequence
        # 1. Feed from gate to extruder sensor
        # 2. Feed from extruder to toolhead sensor
        # 3. Feed from toolhead sensor to nozzle
        # 4. Prime/purge

        logging.info(f'ToolCommands: Load tool {tool} (not yet fully implemented)')
        self.gcode.respond_info('ACE: Load sequence (simplified)')

    def cmd_ACE_FEED(self, gcmd):
        """
        ACE_FEED INDEX=<n> LENGTH=<mm> [SPEED=<mm/s>]

        Feed filament from specified gate.
        """
        gate = gcmd.get_int('INDEX')
        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', self.controller.feed_speed)

        if gate < 0 or gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')

        try:
            device, local_gate = self.device_manager.get_device_for_gate(gate)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")
                else:
                    self.gcode.respond_info(f'ACE: Fed {length}mm from gate {gate}')

            device.feed(local_gate, length, speed, callback)
            device.wait_ready()

        except ValueError as e:
            raise gcmd.error(str(e))

    def cmd_ACE_RETRACT(self, gcmd):
        """
        ACE_RETRACT INDEX=<n> LENGTH=<mm> [SPEED=<mm/s>]

        Retract filament to specified gate.
        """
        gate = gcmd.get_int('INDEX')
        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', self.controller.retract_speed)

        if gate < 0 or gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')

        try:
            device, local_gate = self.device_manager.get_device_for_gate(gate)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")
                else:
                    self.gcode.respond_info(f'ACE: Retracted {length}mm to gate {gate}')

            device.retract(local_gate, length, speed, callback)
            device.wait_ready()

        except ValueError as e:
            raise gcmd.error(str(e))
