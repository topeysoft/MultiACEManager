"""
Tool-related G-code commands for ACE Pro system.

Commands:
- ACE_CHANGE_TOOL - Change to specified tool
- ACE_FEED - Feed filament from gate
- ACE_RETRACT - Retract filament to gate
"""

import logging
from ..exceptions import AceException


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

        self.gcode.register_command(
            'ACE_CLEAR_SELECTION', self.cmd_ACE_CLEAR_SELECTION,
            desc='Clear gate selection without unloading')

        self.gcode.register_command(
            'ACE_SET_GATE', self.cmd_ACE_SET_GATE,
            desc='Set selected gate without loading')

        self.gcode.register_command(
            'ACE_ENABLE_FEED_ASSIST', self.cmd_ACE_ENABLE_FEED_ASSIST,
            desc='Enable feed assist for gate')

        self.gcode.register_command(
            'ACE_DISABLE_FEED_ASSIST', self.cmd_ACE_DISABLE_FEED_ASSIST,
            desc='Disable feed assist for gate')

        logging.info("ToolCommands: Registered ACE_CHANGE_TOOL, ACE_FEED, ACE_RETRACT, ACE_CLEAR_SELECTION, ACE_SET_GATE, ACE_ENABLE_FEED_ASSIST, ACE_DISABLE_FEED_ASSIST")

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

        # Execute pre-toolchange macro
        try:
            self.gcode.run_script_from_command(f'_ACE_PRE_TOOLCHANGE FROM={was} TO={tool}')
        except Exception as e:
            logging.warning(f'ToolCommands: Pre-toolchange macro failed: {e}')

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

        # Execute post-toolchange macro
        try:
            self.gcode.run_script_from_command(f'_ACE_POST_TOOLCHANGE FROM={was} TO={tool}')
        except Exception as e:
            logging.warning(f'ToolCommands: Post-toolchange macro failed: {e}')

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
        self._feed_to_toolhead(tool)

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

    def cmd_ACE_CLEAR_SELECTION(self, gcmd):
        """
        ACE_CLEAR_SELECTION

        Clear selected gate without unloading filament.
        Updates both runtime state and persistent storage.
        Used for UI synchronization when manually removing filament.
        """
        old_tool = self.controller.current_tool

        # Update runtime state
        self.controller.current_tool = -1

        # Update persistent storage
        self.controller.save_variable('ace_current_index', -1, True)

        self.gcode.respond_info(f'ACE: Gate selection cleared (was: {old_tool})')
        logging.info(f'ToolCommands: Cleared gate selection (was: {old_tool})')

    def cmd_ACE_SET_GATE(self, gcmd):
        """
        ACE_SET_GATE GATE=<n>

        Set selected gate without loading filament.
        Updates both runtime state and persistent storage.
        Used for UI synchronization when manually loading filament.

        Args:
            GATE: Gate number to select (-1 to clear, 0-N for specific gate)
        """
        gate = gcmd.get_int('GATE', -1)

        if gate < -1 or gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: -1 or 0-{self.device_manager.total_gates-1})')

        old_tool = self.controller.current_tool

        # Update runtime state
        self.controller.current_tool = gate

        # Update persistent storage
        self.controller.save_variable('ace_current_index', gate, True)

        if gate == -1:
            self.gcode.respond_info('ACE: Gate selection cleared')
            logging.info(f'ToolCommands: Cleared gate selection (was: {old_tool})')
        else:
            self.gcode.respond_info(f'ACE: Selected gate set to {gate} (was: {old_tool})')
            logging.info(f'ToolCommands: Set gate selection: {old_tool} → {gate}')

    def cmd_ACE_ENABLE_FEED_ASSIST(self, gcmd):
        """
        ACE_ENABLE_FEED_ASSIST INDEX=<n>

        Enable feed assist for specified gate.
        Feed assist helps pull filament through the bowden tube during loading.

        Args:
            INDEX: Gate number (0 to total_gates-1)
        """
        gate = gcmd.get_int('INDEX')

        if gate < 0 or gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')

        self._enable_feed_assist(gate)
        self.gcode.respond_info(f'ACE: Feed assist enabled for gate {gate}')

    def cmd_ACE_DISABLE_FEED_ASSIST(self, gcmd):
        """
        ACE_DISABLE_FEED_ASSIST [INDEX=<n>]

        Disable feed assist for specified gate.
        If INDEX not provided, uses currently selected gate.

        Args:
            INDEX: Gate number (optional, defaults to current_tool)
        """
        gate = gcmd.get_int('INDEX', self.controller.current_tool)

        if gate < 0:
            raise gcmd.error('No gate specified and no tool currently selected')

        if gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')

        self._disable_feed_assist(gate)
        self.gcode.respond_info(f'ACE: Feed assist disabled for gate {gate}')

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
        Monitors extruder sensor and stops feeding when triggered.

        Args:
            tool: Tool (gate) number
        """
        if self.controller.extruder_sensor is None:
            logging.warning('ToolCommands: No extruder sensor configured, using fixed distance')
            # Fallback to fixed distance feed if no sensor
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
            return

        # Sensor-monitored feeding approach
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            # Wait for device to be ready
            device.wait_ready()

            # Start feeding with extra length (we'll stop when sensor triggers)
            # Feed length + extra distance to ensure we reach the sensor
            feed_length = self.controller.toolchange_feed_length + self.controller.toolhead_homing_max
            feed_speed = self.controller.feed_speed

            def feed_callback(response):
                logging.info(f'ToolCommands: Feed callback received: {response}')
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            # Start the feed operation (non-blocking)
            logging.info(f'ToolCommands: Starting feed - gate={local_gate}, length={feed_length}mm, speed={feed_speed}mm/s')
            device.feed(local_gate, feed_length, feed_speed, feed_callback)
            logging.info(f'ToolCommands: Feed command sent, device ready state: {device.is_ready()}')

            # Track when we started and when to slow down
            start_time = self.reactor.monotonic()
            slowdown_time = self.controller.toolchange_feed_length / self.controller.feed_speed
            has_slowed = False

            # Monitor sensor in a loop
            timeout = 60.0  # 60 second timeout
            sensor_state = self._check_sensor(self.controller.extruder_sensor)
            logging.info(f'ToolCommands: Starting sensor monitoring. Initial state: {sensor_state}, sensor: {self.controller.extruder_sensor}')

            while not self._check_sensor(self.controller.extruder_sensor):
                # Check if we should slow down for accuracy
                elapsed = self.reactor.monotonic() - start_time
                if not has_slowed and elapsed >= slowdown_time:
                    logging.info('ToolCommands: Slowing feed speed for sensor approach')
                    self._set_feeding_speed(tool, self.controller.toolhead_homing_speed)
                    has_slowed = True

                # Check if device finished (sensor never triggered - error)
                if device.is_ready():
                    sensor_state = self._check_sensor(self.controller.extruder_sensor)
                    logging.error(f'ToolCommands: Feed completed but sensor not triggered. Sensor state: {sensor_state}, elapsed: {elapsed:.2f}s, feed_length: {feed_length}mm')

                    # Call error handler macro if configured
                    if self.controller.error_macros:
                        try:
                            error_cmd = f"{self.controller.error_macros} TOOL={tool} ERROR='EXTRUDER_SENSOR_NOT_TRIGGERED' FEED_LENGTH={feed_length} ELAPSED={elapsed:.2f} SENSOR_STATE={sensor_state}"
                            logging.info(f'ToolCommands: Calling error macro: {error_cmd}')
                            self.gcode.run_script_from_command(error_cmd)
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')

                    raise AceException(f'ACE Error: Load failed - extruder sensor not triggered (fed {feed_length}mm in {elapsed:.1f}s)')

                # Check for timeout
                if elapsed > timeout:
                    self._stop_feeding(tool)
                    raise AceException(f'ACE Error: Load timeout - extruder sensor not triggered after {timeout}s')

                # Small delay before checking again (10ms polling)
                self.dwell(delay=0.01)

            # Sensor triggered! Stop feeding immediately
            logging.info('ToolCommands: Extruder sensor triggered, stopping feed')
            self._stop_feeding(tool)

            # Wait for device to complete the stop
            device.wait_ready()

            logging.info('ToolCommands: Successfully fed to extruder sensor')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to feed to extruder: {e}')
            raise

    def _feed_to_toolhead(self, tool):
        """
        Feed filament from extruder sensor to toolhead sensor using extruder motor.
        Monitors toolhead sensor and stops when triggered.

        Args:
            tool: Tool (gate) number for feed assist
        """
        if self.controller.toolhead_sensor is None:
            logging.warning('ToolCommands: No toolhead sensor configured, using fixed distance')
            # Feed a default distance if no sensor
            self._extruder_move(self.controller.toolhead_homing_max, self.controller.extruder_move_speed)
            return

        # Enable feed assist to help pull filament through
        self._enable_feed_assist(tool)

        # Wait a moment for feed assist to engage
        self.dwell(delay=0.1)

        # Incrementally move extruder while monitoring toolhead sensor
        timeout = 60.0  # 60 second timeout
        start_time = self.reactor.monotonic()

        logging.info('ToolCommands: Feeding to toolhead sensor with incremental moves')

        while not self._check_sensor(self.controller.toolhead_sensor):
            # Check for timeout
            elapsed = self.reactor.monotonic() - start_time
            if elapsed > timeout:
                self._disable_feed_assist(tool)
                raise AceException(f'ACE Error: Load timeout - toolhead sensor not triggered after {timeout}s')

            # Move 1mm at a time
            self._extruder_move(1.0, self.controller.extruder_move_speed)

            # Small delay before next move (10ms polling)
            self.dwell(delay=0.01)

        # Sensor triggered! Disable feed assist
        logging.info('ToolCommands: Toolhead sensor triggered')
        self._disable_feed_assist(tool)

        logging.info('ToolCommands: Successfully fed to toolhead sensor')

    def _feed_to_nozzle(self):
        """
        Feed filament from toolhead sensor to nozzle.
        """
        # Feed the configured sensor-to-nozzle distance
        feed_length = self.controller.toolhead_sensor_to_nozzle_length
        if feed_length > 0:
            self._extruder_move(feed_length, self.controller.extruder_move_speed)

    def dwell(self, delay=1.0):
        """
        Pause reactor for specified delay.

        Args:
            delay: Time to pause in seconds
        """
        curr_time = self.reactor.monotonic()
        self.reactor.pause(curr_time + delay)

    def _stop_feeding(self, tool):
        """
        Stop feeding for specified tool.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            device.stop_feeding(local_gate, callback)

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to stop feeding: {e}')

    def _set_feeding_speed(self, tool, speed):
        """
        Update feeding speed for specified tool.

        Args:
            tool: Tool (gate) number
            speed: New feed speed in mm/s
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            device.update_feeding_speed(local_gate, speed, callback)

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to update feeding speed: {e}')

    def _enable_feed_assist(self, tool):
        """
        Enable feed assist for specified tool.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")
                else:
                    # Update controller state on success
                    self.controller.gate_feed_assist[tool] = True

            device.start_feed_assist(local_gate, callback)
            logging.info(f'ToolCommands: Enabled feed assist for tool {tool}')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to enable feed assist: {e}')

    def _disable_feed_assist(self, tool):
        """
        Disable feed assist for specified tool.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")
                else:
                    # Update controller state on success
                    self.controller.gate_feed_assist[tool] = False

            device.stop_feed_assist(local_gate, callback)
            logging.info(f'ToolCommands: Disabled feed assist for tool {tool}')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to disable feed assist: {e}')
