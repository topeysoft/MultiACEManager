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

        self.gcode.register_command(
            'ACE_RETRY_FEED', self.cmd_ACE_RETRY_FEED,
            desc='Retry failed feed operation after user intervention')

        self.gcode.register_command(
            'ACE_CANCEL_FEED', self.cmd_ACE_CANCEL_FEED,
            desc='Cancel failed feed operation and abort tool change')

        logging.info("ToolCommands: Registered ACE_CHANGE_TOOL, ACE_FEED, ACE_RETRACT, ACE_CLEAR_SELECTION, ACE_SET_GATE, ACE_ENABLE_FEED_ASSIST, ACE_DISABLE_FEED_ASSIST, ACE_RETRY_FEED, ACE_CANCEL_FEED")

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

        Sequence:
        1. Small retract from nozzle to prevent oozing
        2. Tip cutting (while filament still at/near nozzle)
        3. Retract to extruder sensor (with ACE feed assist)
        4. Full retract to gate

        Args:
            tool: Tool (gate) number to unload
        """
        self.gcode.respond_info(f'ACE: Unloading tool {tool}...')

        # 1. Small retract from nozzle to prevent oozing during cut
        retract_for_cut = self.controller.toolchange_retract_for_cut
        if retract_for_cut > 0:
            self.gcode.respond_info(f'ACE: Retracting {retract_for_cut}mm to prevent oozing')
            self._extruder_move(-retract_for_cut, self.controller.extruder_move_speed)

        # 2. Execute tip cutting (while filament at/near nozzle)
        if self.controller.cut_macros:
            self.gcode.respond_info(f'ACE: Executing cut macro: {self.controller.cut_macros}')
            try:
                self.gcode.run_script_from_command(self.controller.cut_macros)
            except Exception as e:
                logging.warning(f'ToolCommands: Cut macro failed: {e}')

        # 3. Retract to extruder sensor (with ACE feed assist)
        extruder_has_filament = self._check_sensor(self.controller.extruder_sensor)
        if extruder_has_filament:
            self.gcode.respond_info('ACE: Retracting to extruder sensor')
            self._retract_from_toolhead(tool)

        # 4. Full retract to gate
        self.gcode.respond_info('ACE: Retracting to gate')
        self._retract_to_gate(tool)

        # 5. Execute poop macros if configured (for waste purge)
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

    def cmd_ACE_RETRY_FEED(self, gcmd):
        """
        ACE_RETRY_FEED

        Retry a failed feed operation after user has cleared the obstruction.
        This command is used after a feed timeout has paused the print.
        """
        if not hasattr(self.controller, 'feed_retry_state') or self.controller.feed_retry_state is None:
            raise gcmd.error('No feed retry pending. This command is only available after a feed timeout.')

        retry_state = self.controller.feed_retry_state
        tool = retry_state['tool']
        retry_count = retry_state['retry_count']
        prev_distance = retry_state['distance_fed']

        self.gcode.respond_info(f'ACE: Retrying feed for tool {tool} (attempt {retry_count + 1}/3, previously fed {prev_distance}mm)')
        logging.info(f'ToolCommands: User initiated feed retry for tool {tool}, retry {retry_count}/2')

        # Clear retry state
        self.controller.feed_retry_state = None

        # Resume print first
        self.gcode.run_script_from_command("RESUME")

        # Retry the feed operation
        try:
            self._feed_to_toolhead(tool, retry_count)
            self.gcode.respond_info(f'ACE: Feed retry successful for tool {tool}')
        except AceException as e:
            # If it fails again, it will either prompt for another retry or raise the exception
            logging.error(f'ToolCommands: Feed retry failed: {e}')
            raise

    def cmd_ACE_CANCEL_FEED(self, gcmd):
        """
        ACE_CANCEL_FEED

        Cancel a failed feed operation and abort the tool change.
        This will cancel the print job.
        """
        if not hasattr(self.controller, 'feed_retry_state') or self.controller.feed_retry_state is None:
            raise gcmd.error('No feed retry pending. This command is only available after a feed timeout.')

        retry_state = self.controller.feed_retry_state
        tool = retry_state['tool']
        distance_fed = retry_state['distance_fed']

        self.gcode.respond_info(f'ACE: Canceling feed operation for tool {tool} (fed {distance_fed}mm before timeout)')
        logging.info(f'ToolCommands: User canceled feed operation for tool {tool}')

        # Clear retry state
        self.controller.feed_retry_state = None

        # Cancel the print
        self.gcode.run_script_from_command("CANCEL_PRINT")

        raise AceException(f'ACE Error: Feed operation canceled by user after timeout (fed {distance_fed}mm)')

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

    def _retract_from_toolhead(self, tool):
        """
        Retract filament from toolhead sensor to extruder sensor.
        Uses extruder motor to retract while ACE provides gentle pull assist.
        Monitors extruder sensor and stops when filament clears.

        Args:
            tool: Tool (gate) number for feed assist
        """
        if self.controller.extruder_sensor is None:
            logging.warning('ToolCommands: No extruder sensor configured, skipping homing retract')
            return

        # Enable ACE feed assist to help pull filament through extruder sensor
        self._enable_feed_assist(tool)
        self.dwell(delay=0.1)  # Let feed assist engage

        # Retract with extruder motor while monitoring sensor
        max_retract = self.controller.toolhead_homing_max
        homing_speed = self.controller.toolhead_homing_speed

        # Start extruder retract in small increments, monitoring sensor
        distance_retracted = 0.0
        increment = 5.0  # Retract in 5mm increments

        logging.info('ToolCommands: Retracting from toolhead to extruder sensor with feed assist')

        while distance_retracted < max_retract:
            # Check if sensor has cleared
            if not self._check_sensor(self.controller.extruder_sensor):
                logging.info(f'ToolCommands: Extruder sensor cleared after {distance_retracted}mm')
                break

            # Retract another increment
            self._extruder_move(-increment, homing_speed)
            distance_retracted += increment
            self.dwell(delay=0.05)  # Small delay for sensor to update

        # Disable feed assist
        self._disable_feed_assist(tool)

        if distance_retracted >= max_retract:
            logging.warning(f'ToolCommands: Reached max retract ({max_retract}mm) but sensor still triggered')
        else:
            logging.info(f'ToolCommands: Successfully retracted {distance_retracted}mm to clear extruder sensor')

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

            # Check gate status before feeding
            device_info = device.get_status()
            gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}
            logging.info(f'ToolCommands: Gate {local_gate} status before feed: {gate_status}')

            # Start feeding configured bowden length (sensor monitoring will stop when triggered)
            feed_length = self.controller.toolchange_feed_length
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

            # Monitor sensor in a loop using direct pin queries for real-time detection
            timeout = 60.0  # 60 second timeout
            sensor_state = self.controller.query_sensor_pin(self.controller.extruder_sensor)
            logging.info(f'ToolCommands: Starting sensor monitoring. Initial state: {sensor_state}, sensor: {self.controller.extruder_sensor}')

            while not self.controller.query_sensor_pin(self.controller.extruder_sensor):
                # Check if we should slow down for accuracy
                elapsed = self.reactor.monotonic() - start_time
                if not has_slowed and elapsed >= slowdown_time:
                    logging.info('ToolCommands: Slowing feed speed for sensor approach')
                    self._set_feeding_speed(tool, self.controller.toolhead_homing_speed)
                    has_slowed = True

                # Check if device finished (sensor never triggered - error)
                if device.is_ready():
                    sensor_state = self.controller.query_sensor_pin(self.controller.extruder_sensor)
                    device_info = device.get_status()
                    gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}
                    logging.error(f'ToolCommands: Feed completed but sensor not triggered.')
                    logging.error(f'  Sensor state: {sensor_state}, elapsed: {elapsed:.2f}s, feed_length: {feed_length}mm')
                    logging.error(f'  Gate {local_gate} status after feed: {gate_status}')
                    logging.error(f'  Device status: {device_info.get("status")}')

                    # Call error handler macro if configured
                    error_msg = f'ACE Error: Load failed - extruder sensor not triggered (fed {feed_length}mm in {elapsed:.1f}s)'
                    if self.controller.error_macros:
                        try:
                            error_cmd = f"{self.controller.error_macros} TOOL={tool} ERROR='EXTRUDER_SENSOR_NOT_TRIGGERED' FEED_LENGTH={feed_length} ELAPSED={elapsed:.2f} SENSOR_STATE={sensor_state}"
                            logging.info(f'ToolCommands: Calling error macro: {error_cmd}')
                            self.gcode.run_script_from_command(error_cmd)
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')
                        # Return after calling error macro - don't shutdown
                        self.gcode.respond_info(error_msg)
                        return
                    else:
                        # No error macro configured - raise exception (will cause shutdown)
                        raise AceException(error_msg)

                # Check for timeout
                if elapsed > timeout:
                    self._stop_feeding(tool)
                    error_msg = f'ACE Error: Load timeout - extruder sensor not triggered after {timeout}s'
                    logging.error(f'ToolCommands: {error_msg}')
                    if self.controller.error_macros:
                        try:
                            error_cmd = f"{self.controller.error_macros} TOOL={tool} ERROR='TIMEOUT' FEED_LENGTH={feed_length} ELAPSED={elapsed:.2f} SENSOR_STATE={sensor_state}"
                            self.gcode.run_script_from_command(error_cmd)
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')
                        self.gcode.respond_info(error_msg)
                        return
                    else:
                        raise AceException(error_msg)

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

    def _feed_to_toolhead(self, tool, retry_count=0):
        """
        Feed filament from extruder sensor to toolhead sensor using extruder motor.
        Monitors toolhead sensor and stops when triggered.

        Args:
            tool: Tool (gate) number for feed assist
            retry_count: Current retry attempt (internal use)
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

        # Incrementally move extruder while monitoring toolhead sensor using direct pin queries
        timeout = 60.0  # 60 second timeout
        start_time = self.reactor.monotonic()
        distance_fed = 0.0

        logging.info('ToolCommands: Feeding to toolhead sensor with incremental moves')

        while not self.controller.query_sensor_pin(self.controller.toolhead_sensor):
            # Check for timeout
            elapsed = self.reactor.monotonic() - start_time
            if elapsed > timeout:
                self._disable_feed_assist(tool)
                logging.error(f'ToolCommands: Load timeout after {elapsed:.1f}s - fed {distance_fed}mm without triggering toolhead sensor')

                # Offer retry with user intervention
                if retry_count < 2:  # Allow up to 2 retries (3 total attempts)
                    self._handle_feed_timeout_retry(tool, distance_fed, retry_count)
                    return
                else:
                    raise AceException(f'ACE Error: Load timeout - toolhead sensor not triggered after {timeout}s (fed {distance_fed}mm). Maximum retries exceeded.')

            # Move 1mm at a time
            self._extruder_move(1.0, self.controller.extruder_move_speed)
            distance_fed += 1.0

            # Small delay before next move (10ms polling)
            self.dwell(delay=0.01)

        # Sensor triggered! Disable feed assist
        logging.info('ToolCommands: Toolhead sensor triggered')
        self._disable_feed_assist(tool)

        logging.info('ToolCommands: Successfully fed to toolhead sensor')

    def _handle_feed_timeout_retry(self, tool, distance_fed, retry_count):
        """
        Handle feed timeout with user intervention prompt and retry logic.

        Args:
            tool: Tool (gate) number
            distance_fed: Distance fed before timeout
            retry_count: Current retry attempt
        """
        retry_num = retry_count + 1

        # Pause the print
        self.gcode.run_script_from_command("PAUSE")

        # Send detailed message to user
        msg = (f"ACE Load Error: Toolhead sensor not triggered after feeding {distance_fed}mm.\n"
               f"Possible causes:\n"
               f"  - Filament jam or tangle\n"
               f"  - Extruder skipping steps\n"
               f"  - Debris blocking sensor\n"
               f"  - Bowden tube disconnected\n\n"
               f"Check the filament path and clear any obstructions.\n"
               f"Use ACE_RETRY_FEED to retry, or ACE_CANCEL_FEED to abort.")

        self.gcode.respond_info(msg)
        logging.warning(f'ToolCommands: Feed timeout - waiting for user intervention (retry {retry_num}/2)')

        # Store retry state for resume command
        self.controller.feed_retry_state = {
            'tool': tool,
            'retry_count': retry_num,
            'distance_fed': distance_fed
        }

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
