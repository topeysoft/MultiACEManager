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

        Sequence (matches BunnyACE):
        1. Disable feed assist for old tool
        2. Tip cutting (at nozzle)
        3. Synchronized retract until extruder sensor clears (extruder + ACE together)
        4. Full retract to gate

        Args:
            tool: Tool (gate) number to unload
        """
        self.gcode.respond_info(f'ACE: Unloading tool {tool}...')

        # 1. Disable feed assist for old tool
        self._disable_feed_assist(tool)

        # Wait for ACE device to be ready
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)
            device.wait_ready()
        except ValueError as e:
            logging.error(f'ToolCommands: Failed to get device for tool {tool}: {e}')
            raise

        # 2. Execute tip cutting (at nozzle position)
        if self.controller.cut_macros:
            self.gcode.respond_info(f'ACE: Executing cut macro: {self.controller.cut_macros}')
            try:
                self.gcode.run_script_from_command(self.controller.cut_macros)
            except Exception as e:
                logging.warning(f'ToolCommands: Cut macro failed: {e}')

        # 3. Synchronized retract until extruder sensor clears
        # Extruder motor pushes back while ACE pulls - work together in 20mm increments
        extruder_has_filament = self._check_sensor(self.controller.extruder_sensor)
        if extruder_has_filament:
            self.gcode.respond_info('ACE: Retracting to extruder sensor (synchronized)')

            def retract_callback(response):
                if 'code' in response and response['code'] != 0:
                    logging.error(f"ACE retract error: {response.get('msg', 'Unknown error')}")

            # Retract in 20mm increments until sensor clears
            while self._check_sensor(self.controller.extruder_sensor):
                # Extruder motor pushes back
                self._extruder_move(-20, self.controller.extruder_move_speed)

                # ACE pulls simultaneously
                device.retract(local_gate, 20, self.controller.retract_speed, retract_callback)
                device.wait_ready()

            logging.info('ToolCommands: Extruder sensor cleared')

        # 4. Full retract to gate
        self.gcode.respond_info('ACE: Retracting to gate')
        self._retract_to_gate(tool)

        logging.info(f'ToolCommands: Unload tool {tool} complete')
        self.gcode.respond_info('ACE: Unload complete')

    def _load_tool(self, tool):
        """
        Load filament for specified tool.

        Supports two configurations:
        - Dual sensor (extruder + toolhead): 3-step feed (gate→extruder→toolhead→nozzle)
        - Single sensor (extruder only): 2-step feed (gate→extruder→nozzle)

        Args:
            tool: Tool (gate) number to load
        """
        self.gcode.respond_info(f'ACE: Loading tool {tool}...')

        # 1. Feed from gate to extruder sensor (always required)
        self.gcode.respond_info('ACE: Feeding from gate to extruder')
        self._feed_to_extruder(tool)

        # Check if we have a toolhead sensor
        if self.controller.toolhead_sensor is not None:
            # Dual sensor configuration: feed extruder→toolhead→nozzle
            # 2. Feed from extruder to toolhead sensor
            self.gcode.respond_info('ACE: Feeding to toolhead sensor')
            self._feed_to_toolhead(tool)

            # 3. Feed from toolhead sensor to nozzle
            self.gcode.respond_info('ACE: Feeding to nozzle')
            self._feed_to_nozzle()
        else:
            # Single sensor configuration: feed extruder→nozzle in one step
            self.gcode.respond_info('ACE: Feeding to nozzle (single sensor mode)')
            self._feed_extruder_to_nozzle()

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

        Uses incremental feeding approach to minimize overshoot:
        - Fast phase: Feed in 50mm chunks until near expected distance
        - Slow phase: Feed in 10mm chunks for precise sensor detection

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

        # Incremental sensor-monitored feeding approach
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            # Wait for device to be ready
            device.wait_ready()

            # Check gate status before feeding
            device_info = device.get_status()
            gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}
            logging.info(f'ToolCommands: Gate {local_gate} status before feed: {gate_status}')

            # Incremental feeding parameters
            total_distance = self.controller.toolchange_feed_length
            fast_chunk_size = 50  # mm - fast feeding in larger chunks
            slow_chunk_size = 10  # mm - slow feeding for precision
            slowdown_margin = 100  # mm - switch to slow chunks when within this distance
            distance_fed = 0.0
            fast_speed = self.controller.feed_speed
            slow_speed = self.controller.toolhead_homing_speed
            timeout = 60.0  # 60 second timeout
            start_time = self.reactor.monotonic()

            def feed_callback(response):
                logging.debug(f'ToolCommands: Feed callback received: {response}')
                if 'code' in response and response['code'] != 0:
                    self.gcode.respond_info(f"ACE Error: {response.get('msg', 'Unknown error')}")

            logging.info(f'ToolCommands: Starting incremental feed to extruder sensor (target: {total_distance}mm)')

            # Feed in chunks until sensor triggers
            while not self.controller.query_sensor_pin(self.controller.extruder_sensor):
                # Check for timeout
                elapsed = self.reactor.monotonic() - start_time
                if elapsed > timeout:
                    error_msg = f'ACE Error: Load timeout - extruder sensor not triggered after {timeout}s (fed {distance_fed}mm)'
                    logging.error(f'ToolCommands: {error_msg}')
                    if self.controller.error_macros:
                        try:
                            sensor_state = self.controller.query_sensor_pin(self.controller.extruder_sensor)
                            error_cmd = f"{self.controller.error_macros} TOOL={tool} ERROR='TIMEOUT' FEED_LENGTH={distance_fed} ELAPSED={elapsed:.2f} SENSOR_STATE={sensor_state}"
                            self.gcode.run_script_from_command(error_cmd)
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')
                        self.gcode.respond_info(error_msg)
                        return
                    else:
                        raise AceException(error_msg)

                # Determine chunk size and speed based on distance remaining
                distance_remaining = total_distance - distance_fed

                if distance_remaining <= slowdown_margin:
                    # Slow phase: small chunks for precision
                    chunk_size = min(slow_chunk_size, distance_remaining + slowdown_margin)
                    speed = slow_speed
                    if distance_fed > 0:  # Log only after first chunk
                        logging.info(f'ToolCommands: Entering slow feed mode at {distance_fed}mm (remaining: {distance_remaining}mm)')
                else:
                    # Fast phase: larger chunks for speed
                    chunk_size = fast_chunk_size
                    speed = fast_speed

                # Feed one chunk
                logging.debug(f'ToolCommands: Feeding chunk {chunk_size}mm at {speed}mm/s (total fed: {distance_fed}mm)')
                device.feed(local_gate, chunk_size, speed, feed_callback)
                device.wait_ready()
                distance_fed += chunk_size

                # Quick sensor check immediately after chunk completes
                if self.controller.query_sensor_pin(self.controller.extruder_sensor):
                    logging.info(f'ToolCommands: Extruder sensor triggered after feeding {distance_fed}mm')
                    break

                # Check if we've exceeded expected distance without trigger
                if distance_fed > total_distance + slowdown_margin:
                    sensor_state = self.controller.query_sensor_pin(self.controller.extruder_sensor)
                    device_info = device.get_status()
                    gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}
                    elapsed = self.reactor.monotonic() - start_time
                    logging.error(f'ToolCommands: Fed {distance_fed}mm (expected: {total_distance}mm) without triggering sensor')
                    logging.error(f'  Sensor state: {sensor_state}, elapsed: {elapsed:.2f}s')
                    logging.error(f'  Gate {local_gate} status: {gate_status}')

                    # Call error handler macro if configured
                    error_msg = f'ACE Error: Load failed - extruder sensor not triggered (fed {distance_fed}mm, expected {total_distance}mm)'
                    if self.controller.error_macros:
                        try:
                            error_cmd = f"{self.controller.error_macros} TOOL={tool} ERROR='EXTRUDER_SENSOR_NOT_TRIGGERED' FEED_LENGTH={distance_fed} ELAPSED={elapsed:.2f} SENSOR_STATE={sensor_state}"
                            logging.info(f'ToolCommands: Calling error macro: {error_cmd}')
                            self.gcode.run_script_from_command(error_cmd)
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')
                        self.gcode.respond_info(error_msg)
                        return
                    else:
                        raise AceException(error_msg)

            # Sensor triggered successfully!
            logging.info(f'ToolCommands: Extruder sensor triggered at {distance_fed}mm (expected: {total_distance}mm, delta: {distance_fed - total_distance:+.1f}mm)')

            # Apply overshoot compensation if configured
            if self.controller.sensor_overshoot_compensation > 0:
                compensation = self.controller.sensor_overshoot_compensation
                logging.info(f'ToolCommands: Applying overshoot compensation: retracting {compensation}mm')

                def retract_callback(response):
                    if 'code' in response and response['code'] != 0:
                        logging.warning(f"ToolCommands: Overshoot compensation retract failed: {response.get('msg', 'Unknown error')}")

                device.retract(local_gate, compensation, self.controller.retract_speed, retract_callback)
                device.wait_ready()

                # Verify sensor still triggered after compensation
                if not self.controller.query_sensor_pin(self.controller.extruder_sensor):
                    logging.warning(f'ToolCommands: Warning - extruder sensor cleared after {compensation}mm compensation retract')
                    logging.warning('ToolCommands: This may indicate compensation is too large or sensor is intermittent')

            # Enable feed assist for subsequent extruder operations
            # This matches BunnyACE: enable AFTER extruder sensor triggers
            self._enable_feed_assist(tool)

            logging.info('ToolCommands: Successfully fed to extruder sensor, feed assist enabled')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to feed to extruder: {e}')
            raise

    def _feed_to_toolhead(self, tool, retry_count=0):
        """
        Feed filament from extruder sensor to toolhead sensor using extruder motor.
        Monitors toolhead sensor and stops when triggered.

        NOTE: This method should only be called in dual-sensor configurations.
        For single-sensor configs, use _feed_extruder_to_nozzle() instead.

        NOTE: Feed assist is already enabled in _feed_to_extruder() and stays ON
        through entire load sequence (matches BunnyACE).

        Args:
            tool: Tool (gate) number for feed assist
            retry_count: Current retry attempt (internal use)
        """
        if self.controller.toolhead_sensor is None:
            logging.error('ToolCommands: _feed_to_toolhead called but no toolhead sensor configured!')
            logging.error('This should not happen - check _load_tool logic')
            # Fallback: feed a default distance
            self._extruder_move(self.controller.toolhead_homing_max, self.controller.extruder_move_speed)
            return

        # Feed assist already enabled in _feed_to_extruder() - just use it
        # Incrementally move extruder while monitoring toolhead sensor using direct pin queries
        timeout = 60.0  # 60 second timeout
        start_time = self.reactor.monotonic()
        distance_fed = 0.0

        logging.info('ToolCommands: Feeding to toolhead sensor (with feed assist)')

        while not self.controller.query_sensor_pin(self.controller.toolhead_sensor):
            # Check for timeout
            elapsed = self.reactor.monotonic() - start_time
            if elapsed > timeout:
                # Disable feed assist on error
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

        # Sensor triggered! Feed assist stays ON for nozzle feed and poop macro
        logging.info('ToolCommands: Toolhead sensor triggered (feed assist remains active)')
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
        Used in dual-sensor configurations.
        """
        # Feed the configured sensor-to-nozzle distance
        feed_length = self.controller.toolhead_sensor_to_nozzle_length
        if feed_length > 0:
            self._extruder_move(feed_length, self.controller.extruder_move_speed)

    def _feed_extruder_to_nozzle(self):
        """
        Feed filament from extruder sensor directly to nozzle.
        Used in single-sensor configurations (no toolhead sensor).
        """
        # Use configured extruder_sensor_to_nozzle distance, or fallback to toolhead_homing_max
        feed_length = self.controller.extruder_sensor_to_nozzle_length
        if feed_length == 0:
            # Fallback: use toolhead_homing_max if extruder_sensor_to_nozzle not configured
            feed_length = self.controller.toolhead_homing_max
            logging.warning(f'ToolCommands: extruder_sensor_to_nozzle not configured, using toolhead_homing_max ({feed_length}mm) as fallback')

        if feed_length > 0:
            logging.info(f'ToolCommands: Feeding {feed_length}mm from extruder sensor to nozzle (single sensor mode)')
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
