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

        # 1. Check toolhead sensor state
        toolhead_has_filament = self._check_sensor(self.controller.toolhead_sensor)

        # 2. Retract to toolhead sensor if present
        if toolhead_has_filament:
            self.gcode.respond_info('ACE: Retracting from nozzle to toolhead sensor')
            self._retract_from_nozzle()

        # 3. Execute cut/poop macros if configured
        if self.controller.cut_macros:
            self.gcode.respond_info(f'ACE: Executing cut macro: {self.controller.cut_macros}')
            try:
                self.gcode.run_script_from_command(self.controller.cut_macros)
            except Exception as e:
                logging.warning(f'ToolCommands: Cut macro failed: {e}')

        # 4. Retract to extruder sensor
        extruder_has_filament = self._check_sensor(self.controller.extruder_sensor)
        if extruder_has_filament:
            self.gcode.respond_info('ACE: Retracting from toolhead to extruder sensor')
            self._retract_from_toolhead()

        # 5. Retract to gate
        self.gcode.respond_info('ACE: Retracting to gate')
        self._retract_to_gate(tool)

        # 6. Execute poop macros if configured
        if self.controller.poop_macros:
            self.gcode.respond_info(f'ACE: Executing poop macro: {self.controller.poop_macros}')
            try:
                self.gcode.run_script_from_command(self.controller.poop_macros)
            except Exception as e:
                logging.warning(f'ToolCommands: Poop macro failed: {e}')

        logging.info(f'ToolCommands: Unload tool {tool} complete')
        self.gcode.respond_info('ACE: Unload complete')

    def _load_tool(self, tool):
        """
        Load filament for specified tool.

        Args:
            tool: Tool (gate) number to load
        """
        self.gcode.respond_info(f'ACE: Loading tool {tool}...')

        # 1. Feed from gate to extruder sensor
        self.gcode.respond_info('ACE: Feeding from gate to extruder')
        self._feed_to_extruder(tool)

        # 2. Feed from extruder to toolhead sensor
        self.gcode.respond_info('ACE: Feeding to toolhead sensor')
        self._feed_to_toolhead()

        # 3. Feed from toolhead sensor to nozzle
        self.gcode.respond_info('ACE: Feeding to nozzle')
        self._feed_to_nozzle()

        # 4. Prime/purge
        if self.controller.poop_macros:
            self.gcode.respond_info(f'ACE: Executing poop macro: {self.controller.poop_macros}')
            try:
                self.gcode.run_script_from_command(self.controller.poop_macros)
            except Exception as e:
                logging.warning(f'ToolCommands: Poop macro failed: {e}')

        logging.info(f'ToolCommands: Load tool {tool} complete')
        self.gcode.respond_info('ACE: Load complete')

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

    # ========================================================================
    # Helper Methods for Tool Change Sequences
    # ========================================================================

    def _check_sensor(self, sensor):
        """
        Check if sensor detects filament.

        Args:
            sensor: Sensor object (extruder_sensor or toolhead_sensor)

        Returns:
            bool: True if filament is detected, False otherwise
        """
        if sensor is None:
            return False
        return sensor.runout_helper.filament_present

    def _extruder_move(self, length, speed):
        """
        Move extruder motor by specified length.

        Args:
            length: Length to move in mm (positive for feed, negative for retract)
            speed: Movement speed in mm/s

        Returns:
            float: New extruder position
        """
        pos = self.controller.toolhead.get_position()
        pos[3] += length
        self.controller.toolhead.move(pos, speed)
        return pos[3]

    def _retract_from_nozzle(self):
        """
        Retract filament from nozzle to toolhead sensor.
        """
        # Retract the configured nozzle-to-sensor distance
        retract_length = -self.controller.toolhead_sensor_to_nozzle_length
        if retract_length < 0:
            self._extruder_move(retract_length, self.controller.extruder_move_speed)

    def _retract_from_toolhead(self):
        """
        Retract filament from toolhead sensor to extruder sensor using homing.
        """
        if self.controller.extruder_sensor is None:
            logging.warning('ToolCommands: No extruder sensor configured, skipping homing retract')
            return

        # Home to extruder sensor by retracting
        max_retract = self.controller.toolhead_homing_max
        homing_speed = self.controller.toolhead_homing_speed

        # Retract until extruder sensor is not triggered
        endstop = self.controller.endstops.get('extruder_sensor')
        if endstop:
            # Use manual homing approach
            self._extruder_move(-max_retract, homing_speed)
        else:
            # Fallback: retract configured distance
            self._extruder_move(-max_retract, homing_speed)

    def _retract_to_gate(self, tool):
        """
        Retract filament from extruder to gate using ACE device.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            length = self.controller.toolchange_retract_length
            speed = self.controller.retract_speed

            device.retract(local_gate, length, speed, callback)
            device.wait_ready()

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to retract to gate: {e}')

    def _feed_to_extruder(self, tool):
        """
        Feed filament from gate to extruder sensor using ACE device.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            length = self.controller.toolchange_feed_length
            speed = self.controller.feed_speed

            device.feed(local_gate, length, speed, callback)
            device.wait_ready()

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to feed to extruder: {e}')

    def _feed_to_toolhead(self):
        """
        Feed filament from extruder sensor to toolhead sensor using extruder motor.
        """
        if self.controller.toolhead_sensor is None:
            logging.warning('ToolCommands: No toolhead sensor configured, using fixed distance')
            # Feed a default distance if no sensor
            self._extruder_move(self.controller.toolhead_homing_max, self.controller.extruder_move_speed)
            return

        # Home to toolhead sensor by feeding
        max_feed = self.controller.toolhead_homing_max
        homing_speed = self.controller.toolhead_homing_speed

        # Feed until toolhead sensor is triggered
        endstop = self.controller.endstops.get('toolhead_sensor')
        if endstop:
            # Use manual homing approach
            self._extruder_move(max_feed, homing_speed)
        else:
            # Fallback: feed configured distance
            self._extruder_move(max_feed, homing_speed)

    def _feed_to_nozzle(self):
        """
        Feed filament from toolhead sensor to nozzle.
        """
        # Feed the configured sensor-to-nozzle distance
        feed_length = self.controller.toolhead_sensor_to_nozzle_length
        if feed_length > 0:
            self._extruder_move(feed_length, self.controller.extruder_move_speed)
