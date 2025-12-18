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
        ACE_CHANGE_TOOL TOOL=<n> [SKIP_PREHEAT=0|1]

        Change to specified tool (gate).
        Use TOOL=-1 to unload.
        Optional SKIP_PREHEAT=1 to disable automatic pre-heating for this change.
        """
        tool = gcmd.get_int('TOOL')
        skip_preheat = gcmd.get_int('SKIP_PREHEAT', 0) == 1

        if tool < -1 or tool >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid tool (valid: -1 or 0-{self.device_manager.total_gates-1})')

        was = self.controller.current_tool

        if was == tool:
            self.gcode.respond_info(f'ACE: Already on tool {tool}')
            return

        # Check if currently selected tool is valid (might be stale after device disconnect)
        if was >= self.device_manager.total_gates:
            error_msg = f'Current tool T{was} is out of range (only {self.device_manager.total_gates} gates available). Run ACE_SCAN_DEVICES or ACE_CLEAR_SELECTION first.'
            logging.error(f'ToolCommands: {error_msg}')
            raise gcmd.error(error_msg)

        logging.info(f'ToolCommands: ========================================')
        logging.info(f'ToolCommands: TOOL CHANGE START: {was} => {tool}')
        logging.info(f'ToolCommands: Feed assist states before change: {self.controller.gate_feed_assist}')
        logging.info(f'ToolCommands: ========================================')
        self.gcode.respond_info(f'ACE: Tool change {was} => {tool}')

        # Check if target gate is ready (like BunnyACE line 799-803)
        if tool != -1:
            try:
                device, local_gate = self.device_manager.get_device_for_gate(tool)
                device_info = device.get_status()
                gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}
                status = gate_status.get('status', 'unknown')

                logging.info(f'ToolCommands: Target gate {tool} (local {local_gate}) status: {status}')
                logging.info(f'ToolCommands: Full gate status: {gate_status}')

                if status != 'ready':
                    error_msg = f'ACE Error: Gate {tool} is not ready (status: {status})'
                    logging.error(f'ToolCommands: {error_msg}')
                    self.gcode.respond_info(error_msg)
                    raise gcmd.error(error_msg)
            except ValueError as e:
                logging.error(f'ToolCommands: Failed to check gate status: {e}')

        # Execute pre-toolchange macro
        try:
            self.gcode.run_script_from_command(f'_ACE_PRE_TOOLCHANGE FROM={was} TO={tool}')
        except Exception as e:
            logging.warning(f'ToolCommands: Pre-toolchange macro failed: {e}')

        if tool == -1:
            # Unload sequence
            if was >= 0:
                logging.info(f'ToolCommands: Starting unload of tool {was}')
                self._unload_tool(was)
                logging.info(f'ToolCommands: Unload complete. Feed assist states: {self.controller.gate_feed_assist}')
            else:
                self.gcode.respond_info('ACE: No tool loaded, nothing to unload')
        else:
            # Full tool change sequence
            if was >= 0:
                logging.info(f'ToolCommands: Starting unload of tool {was}')
                self._unload_tool(was)
                logging.info(f'ToolCommands: Unload complete. Feed assist states: {self.controller.gate_feed_assist}')

                # Ensure ALL devices are idle before starting load
                # This prevents cross-device race conditions where one device starts feeding
                # while another is still retracting
                logging.info('ToolCommands: Waiting for all ACE devices to become idle...')
                self.device_manager.wait_all_devices_ready()
                logging.info('ToolCommands: All ACE devices idle')

                # ACE firmware needs additional time to reset motor controller when
                # switching between gates on same device
                if tool != -1:
                    try:
                        old_device, _ = self.device_manager.get_device_for_gate(was)
                        new_device, _ = self.device_manager.get_device_for_gate(tool)

                        if old_device.device_id == new_device.device_id:
                            logging.info(f'ToolCommands: Same-device tool change detected, adding firmware stabilization delay')
                            self.dwell(delay=1.0)  # Firmware needs ~1s to fully reset motor controller
                            new_device.wait_ready()  # Verify device still ready after delay
                    except ValueError as e:
                        logging.warning(f'ToolCommands: Could not verify device match: {e}')

            logging.info(f'ToolCommands: Starting load of tool {tool}')
            self._load_tool(tool, skip_preheat=skip_preheat)
            logging.info(f'ToolCommands: Load complete. Feed assist states: {self.controller.gate_feed_assist}')

        # Execute post-toolchange macro
        try:
            self.gcode.run_script_from_command(f'_ACE_POST_TOOLCHANGE FROM={was} TO={tool}')
        except Exception as e:
            logging.warning(f'ToolCommands: Post-toolchange macro failed: {e}')

        # Update current tool
        self.controller.current_tool = tool
        self.controller.save_variable('ace_current_index', tool, True)

    def _sequential_retract_to_clear_sensor(self, tool, device, local_gate):
        """
        Sequential retraction strategy to clear extruder sensor.

        Instead of synchronized extruder+ACE retraction, this method uses a sequential approach:
        1. Extruder retracts by configured clearance length, waits for completion
        2. ACE gently pulls 10mm to test if sensor cleared
        3. If sensor clear → success, return
        4. If sensor NOT clear → retry from step 1

        IMPORTANT: This method ONLY clears the sensor. After this completes,
        _retract_to_gate() must be called to pull the full toolchange_retract_length
        to ensure filament clears the splitter.

        Total ACE retraction = (this method's pulls) + toolchange_retract_length

        Args:
            tool: Tool (gate) number
            device: ACE device object
            local_gate: Local gate number on device

        Raises:
            AceException: If sensor doesn't clear after max retries
        """
        max_retries = 5
        clearance_length = self.controller.extruder_clearance_length
        test_pull_length = 10  # Gentle pull to test sensor

        for retry in range(max_retries):
            logging.info(f'ToolCommands: Sequential retract attempt {retry + 1}/{max_retries}')

            # Step 1: Extruder retract only, wait for completion
            logging.info(f'ToolCommands: Step 1 - Extruder retracting {clearance_length}mm')
            self._extruder_move(-clearance_length, self.controller.extruder_move_speed)

            # Wait for extruder move to complete
            self.controller.toolhead.wait_moves()
            logging.info('ToolCommands: Extruder retract complete')

            # Step 2: ACE gentle pull to test sensor
            logging.info(f'ToolCommands: Step 2 - ACE gentle pull {test_pull_length}mm to test sensor')

            def retract_callback(response):
                if 'code' in response and response['code'] != 0:
                    logging.error(f"ACE retract error: {response.get('msg', 'Unknown error')}")

            device.retract(local_gate, test_pull_length, self.controller.retract_speed, retract_callback)

            # Wait for ACE movement
            expected_duration = (test_pull_length / self.controller.retract_speed) + 0.1
            self.dwell(delay=expected_duration)
            device.wait_ready()

            # Step 3: Check if sensor cleared
            sensor_clear = not self._check_sensor(self.controller.extruder_sensor)
            logging.info(f'ToolCommands: Step 3 - Sensor clear: {sensor_clear}')

            if sensor_clear:
                logging.info('ToolCommands: Extruder sensor cleared successfully')
                return  # Success!
            else:
                logging.warning(f'ToolCommands: Sensor still triggered, retry {retry + 1}/{max_retries}')

        # Max retries exceeded
        error_msg = f'ACE Error: Failed to clear extruder sensor after {max_retries} attempts'
        logging.error(f'ToolCommands: {error_msg}')

        if self.controller.error_macros:
            try:
                self.gcode.run_script_from_command(f"{self.controller.error_macros} TOOL={tool} ERROR='EXTRUDER_SENSOR_NOT_CLEAR'")
            except Exception as e:
                logging.error(f'ToolCommands: Error macro failed: {e}')

        raise AceException(error_msg)

    def _unload_tool(self, tool):
        """
        Unload filament from specified tool.

        Sequence:
        1. Disable feed assist for old tool
        2. Tip cutting (at nozzle)
        3. Sequential retract until extruder sensor clears (extruder then ACE, with retry)
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

        # 3. Sequential retract until extruder sensor clears
        # Extruder retracts first, then ACE pulls gently to test, with retry logic
        extruder_has_filament = self._check_sensor(self.controller.extruder_sensor)
        if extruder_has_filament:
            self.gcode.respond_info('ACE: Retracting to clear extruder sensor (sequential)')
            self._sequential_retract_to_clear_sensor(tool, device, local_gate)
            logging.info('ToolCommands: Extruder sensor cleared')

        # 4. Full retract to gate (splitter)
        # ACE pulls the full toolchange_retract_length distance from extruder sensor to splitter
        # This is ADDITIONAL to any pulls done during sensor clearing
        self.gcode.respond_info('ACE: Retracting to gate')
        self._retract_to_gate(tool)

        logging.info(f'ToolCommands: Unload tool {tool} complete')
        self.gcode.respond_info('ACE: Unload complete')

    def _load_tool(self, tool, skip_preheat=False):
        """
        Load filament for specified tool.

        Supports two configurations:
        - Dual sensor (extruder + toolhead): 3-step feed (gate→extruder→toolhead→nozzle)
        - Single sensor (extruder only): 2-step feed (gate→extruder→nozzle)

        Args:
            tool: Tool (gate) number to load
            skip_preheat: If True, skip automatic temperature pre-heating
        """
        self.gcode.respond_info(f'ACE: Loading tool {tool}...')

        # 1. Feed from gate to extruder sensor (always required)
        self.gcode.respond_info('ACE: Feeding from gate to extruder')
        self._feed_to_extruder(tool)

        # 2. Ensure correct temperature BEFORE feeding to nozzle (prevents extrude-below-temp errors)
        self._ensure_temperature(tool, skip_preheat=skip_preheat)

        # Check if we have a toolhead sensor
        if self.controller.toolhead_sensor is not None:
            # Dual sensor configuration: feed extruder→toolhead→nozzle
            # 3. Feed from extruder to toolhead sensor
            self.gcode.respond_info('ACE: Feeding to toolhead sensor')
            self._feed_to_toolhead(tool)

            # 4. Feed from toolhead sensor to nozzle
            self.gcode.respond_info('ACE: Feeding to nozzle')
            self._feed_to_nozzle()
        else:
            # Single sensor configuration: feed extruder→nozzle in one step
            self.gcode.respond_info('ACE: Feeding to nozzle (single sensor mode)')
            self._feed_extruder_to_nozzle()

        # 5. Prime/purge
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

            # Wait for this specific gate to complete movement
            # Using per-gate status is more accurate than device-level status
            # because ACE firmware updates gate status when motors actually stop
            logging.info(f'ToolCommands: Waiting for gate {tool} (local {local_gate}) to complete retract...')
            device.wait_gate_ready(local_gate, timeout=30.0)
            logging.info(f'ToolCommands: Gate {tool} retract complete')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to retract to gate: {e}')

    def _feed_to_extruder(self, tool):
        """
        Feed filament from gate to extruder sensor using ACE device.
        Monitors extruder sensor and stops feeding when triggered.

        This mirrors BunnyACE's _park_to_toolhead() implementation exactly.

        Args:
            tool: Tool (gate) number
        """
        if self.controller.extruder_sensor is None:
            logging.warning('ToolCommands: No extruder sensor configured, using fixed distance')
            # Fallback to fixed distance feed if no sensor
            self._feed_fixed_distance(tool, self.controller.toolchange_feed_length, self.controller.feed_speed)
            return

        # BunnyACE approach: continuous feed with sensor monitoring
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)
            device.wait_ready()

            # Start continuous feed (like BunnyACE line 745-749)
            feed_length = self.controller.toolchange_feed_length + self.controller.toolhead_homing_max
            start_fast_feed = self.reactor.monotonic()

            # Check device and gate status before feeding
            logging.info(f'ToolCommands: Starting feed to extruder sensor')
            logging.info(f'  Device: {device.device_id}, Gate: {local_gate}, Length: {feed_length}mm, Speed: {self.controller.feed_speed}mm/s')
            logging.info(f'  Device ready: {device.is_ready()}')
            logging.info(f'  Feed assist currently: {self.controller.gate_feed_assist[tool] if tool < len(self.controller.gate_feed_assist) else False}')

            # Send feed command with no wait (like BunnyACE _feed with how_wait=0)
            def feed_callback(response):
                logging.info(f"ToolCommands: Feed callback: {response}")
                if 'code' in response and response['code'] != 0:
                    logging.error(f"ToolCommands: ACE Feed FAILED: {response.get('msg', 'Unknown error')}")
                    logging.error(f"  Full response: {response}")
                else:
                    logging.info(f"ToolCommands: Feed command accepted by ACE device")

            logging.info(f'ToolCommands: Sending feed command to ACE...')
            device.feed(local_gate, feed_length, self.controller.feed_speed, feed_callback)
            logging.info(f'ToolCommands: Feed command sent, waiting 0.1s for start...')

            # Small dwell to let command start (like BunnyACE's 0.1s dwell)
            self.dwell(delay=0.1)

            logging.info(f'ToolCommands: After 0.1s dwell, device ready: {device.is_ready()}')

            # Monitor sensor while feeding (like BunnyACE lines 751-760)
            # Use runout_helper.filament_present like BunnyACE does
            # Note: Legacy BunnyACE code checks is_ace_ready() to detect premature stop,
            # but ACE firmware reports 'ready' status immediately after accepting command,
            # not after motor completes movement. So we use timeout instead.
            loop_count = 0
            has_slowed_down = False  # Track whether we've already slowed down
            max_feed_time = (feed_length / self.controller.feed_speed) * 2.0  # 2x expected time as safety margin
            while not bool(self.controller.extruder_sensor.runout_helper.filament_present):
                loop_count += 1

                # Log progress every 100 iterations (~1 second at 10ms polling)
                if loop_count % 100 == 0:
                    elapsed = self.reactor.monotonic() - start_fast_feed
                    estimated_distance = self.controller.feed_speed * elapsed
                    sensor_state = self.controller.extruder_sensor.runout_helper.filament_present
                    logging.info(f'ToolCommands: Feeding progress: {elapsed:.1f}s, ~{estimated_distance:.0f}mm, sensor: {sensor_state}')

                # Slow down when approaching target (like BunnyACE lines 752-755)
                if (not has_slowed_down and
                    (self.reactor.monotonic() - start_fast_feed) >= (self.controller.toolchange_feed_length // self.controller.feed_speed)):
                    logging.info('ToolCommands: Slowing feed speed for precision')
                    self._set_feeding_speed(tool, self.controller.toolhead_homing_speed)
                    has_slowed_down = True  # Only slow down once

                # Timeout check - if feeding takes too long, assume failure
                elapsed = self.reactor.monotonic() - start_fast_feed
                if elapsed > max_feed_time:
                    # Feed timeout - get detailed status
                    device, local_gate = self.device_manager.get_device_for_gate(tool)
                    device_info = device.get_status()
                    gate_status = device_info.get('slots', [{}])[local_gate] if local_gate < len(device_info.get('slots', [])) else {}

                    error_msg = f'ACE Error: Load timeout - extruder sensor not triggered after {elapsed:.1f}s (expected ~{feed_length / self.controller.feed_speed:.1f}s)'
                    logging.error(f'ToolCommands: {error_msg}')
                    logging.error(f'ToolCommands: Gate {tool} (local {local_gate}) status: {gate_status}')
                    logging.error(f'ToolCommands: Device status: {device_info.get("status")}')
                    logging.error(f'ToolCommands: Full device info: {device_info}')

                    if self.controller.error_macros:
                        try:
                            self.gcode.run_script_from_command(f"{self.controller.error_macros} TOOL={tool} ERROR='EXTRUDER_SENSOR_NOT_TRIGGERED'")
                        except Exception as e:
                            logging.error(f'ToolCommands: Error macro failed: {e}')

                    raise AceException(error_msg)

                # Poll delay (like BunnyACE line 759)
                self.dwell(delay=0.01)

            # Sensor triggered! Stop feeding (like BunnyACE line 761)
            logging.info('ToolCommands: Extruder sensor triggered, stopping feed')
            self._stop_feeding(tool)

            # Wait for stop to complete (like BunnyACE line 763)
            device.wait_ready()

            # Apply overshoot compensation if configured
            if self.controller.sensor_overshoot_compensation > 0:
                compensation = self.controller.sensor_overshoot_compensation
                logging.info(f'ToolCommands: Applying overshoot compensation: retracting {compensation}mm')

                def retract_callback(response):
                    if 'code' in response and response['code'] != 0:
                        logging.warning(f"ToolCommands: Overshoot compensation failed: {response.get('msg', 'Unknown error')}")

                device.retract(local_gate, compensation, self.controller.retract_speed, retract_callback)
                device.wait_ready()

                # Verify sensor still triggered
                if not self.controller.query_sensor_pin(self.controller.extruder_sensor):
                    logging.warning(f'ToolCommands: Warning - sensor cleared after {compensation}mm retract (compensation too large?)')

            # Enable feed assist (like BunnyACE line 765)
            self._enable_feed_assist(tool)

            logging.info('ToolCommands: Successfully fed to extruder sensor')

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

        # Verify feed assist is enabled
        if tool < len(self.controller.gate_feed_assist):
            feed_assist_enabled = self.controller.gate_feed_assist[tool]
            if not feed_assist_enabled:
                logging.warning(f'ToolCommands: Feed assist not enabled for gate {tool}! Enabling now...')
                self._enable_feed_assist(tool)
        else:
            # List not large enough - enable feed assist
            logging.warning(f'ToolCommands: gate_feed_assist list too small (size={len(self.controller.gate_feed_assist)}, tool={tool}), enabling feed assist...')
            self._enable_feed_assist(tool)
            feed_assist_enabled = False

        logging.info('ToolCommands: Feeding to toolhead sensor (with feed assist)')
        logging.info(f'  Extruder speed: {self.controller.extruder_move_speed}mm/s, timeout: {timeout}s')
        logging.info(f'  Feed assist enabled: {feed_assist_enabled if tool < len(self.controller.gate_feed_assist) else "unknown"}')

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

    def _ensure_temperature(self, tool, skip_preheat=False):
        """
        Ensure extruder is at correct temperature for tool before purging.

        Checks if current temperature is significantly lower than target gate temperature.
        If delta > threshold and heater is not actively heating, pre-heat to target temp.

        Args:
            tool: Tool (gate) number to check temperature for
            skip_preheat: If True, skip pre-heating even if needed (for manual override)

        Returns:
            bool: True if temperature is ready, False if skipped
        """
        # Skip if feature is disabled or manual override
        if not self.controller.enable_temp_preheat or skip_preheat:
            return True

        # Get target temperature for this gate
        gate_temps = self.save_variables.allVariables.get('ace_gate_temp', [230] * self.device_manager.total_gates)
        if tool < 0 or tool >= len(gate_temps):
            logging.warning(f'ToolCommands: Invalid tool {tool} for temperature check')
            return True

        target_temp = gate_temps[tool]

        # Get current extruder temperature and state
        try:
            extruder = self.controller.printer.lookup_object('extruder')
            current_temp = extruder.get_status(self.reactor.monotonic())['temperature']
            target_set = extruder.get_status(self.reactor.monotonic())['target']

            # Calculate temperature delta
            temp_delta = target_temp - current_temp
            threshold = self.controller.temp_preheat_threshold

            logging.info(f'ToolCommands: Temperature check for T{tool}:')
            logging.info(f'  Current: {current_temp:.1f}°C, Target: {target_temp}°C, Delta: {temp_delta:.1f}°C')
            logging.info(f'  Heater target: {target_set:.1f}°C, Threshold: {threshold}°C')

            # Check if we need to pre-heat
            # Heat if: delta > threshold AND heater is not already actively heating to correct temp
            heater_active = abs(target_set - target_temp) < 5  # Within 5°C means already heating to correct temp

            if temp_delta > threshold and not heater_active:
                # Get gate material for better user messaging
                gate_materials = self.save_variables.allVariables.get('ace_gate_type', [''] * self.device_manager.total_gates)
                material = gate_materials[tool] if tool < len(gate_materials) else 'Unknown'

                self.gcode.respond_info(f'ACE: Temperature mismatch detected')
                self.gcode.respond_info(f'ACE: Current: {current_temp:.1f}°C, Target: {target_temp}°C ({material})')
                self.gcode.respond_info(f'ACE: Pre-heating extruder to {target_temp}°C...')
                logging.info(f'ToolCommands: Pre-heating extruder from {current_temp:.1f}°C to {target_temp}°C for {material}')

                # Set target temperature
                self.gcode.run_script_from_command(f'M104 S{target_temp}')

                # Wait for temperature with progress updates
                self.gcode.run_script_from_command(f'TEMPERATURE_WAIT SENSOR=extruder MINIMUM={target_temp}')

                # Stabilize time to ensure consistent temperature
                stabilize_time = self.controller.temp_stabilize_time
                if stabilize_time > 0:
                    self.gcode.respond_info(f'ACE: Temperature reached, stabilizing for {stabilize_time:.1f}s...')
                    logging.info(f'ToolCommands: Stabilizing temperature for {stabilize_time}s')
                    self.dwell(stabilize_time)

                self.gcode.respond_info(f'ACE: Extruder ready at {target_temp}°C')
                logging.info(f'ToolCommands: Pre-heating complete')
                return True

            elif temp_delta > threshold and heater_active:
                # Heater is already heating to correct temp, just wait for it
                self.gcode.respond_info(f'ACE: Waiting for extruder to reach {target_temp}°C...')
                self.gcode.run_script_from_command(f'TEMPERATURE_WAIT SENSOR=extruder MINIMUM={target_temp}')
                return True

            else:
                # Temperature is already sufficient
                logging.info(f'ToolCommands: Temperature OK (delta {temp_delta:.1f}°C < threshold {threshold}°C)')
                return True

        except Exception as e:
            logging.error(f'ToolCommands: Temperature check failed: {e}')
            # Don't block tool change on temperature check failure
            return True

    def _feed_fixed_distance(self, tool, length, speed):
        """
        Feed fixed distance without sensor monitoring.

        Args:
            tool: Tool (gate) number
            length: Distance to feed in mm
            speed: Feed speed in mm/s
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    logging.error(f"ToolCommands: Feed error: {response.get('msg', 'Unknown error')}")

            device.feed(local_gate, length, speed, callback)
            device.wait_ready()

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to feed: {e}')

    def _is_ready(self, tool):
        """
        Check if ACE device is ready (not feeding).

        Args:
            tool: Tool (gate) number

        Returns:
            bool: True if device is ready
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)
            return device.is_ready()
        except ValueError as e:
            logging.error(f'ToolCommands: Failed to check ready status: {e}')
            return True  # Assume ready on error to avoid infinite loop

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
                    # Update controller state on success (with bounds checking)
                    if tool < len(self.controller.gate_feed_assist):
                        self.controller.gate_feed_assist[tool] = True
                    else:
                        # Extend list if needed
                        while len(self.controller.gate_feed_assist) <= tool:
                            self.controller.gate_feed_assist.append(False)
                        self.controller.gate_feed_assist[tool] = True

            device.start_feed_assist(local_gate, callback)
            device.wait_ready()  # Wait for command to complete

            # ACE firmware needs additional time after response to fully activate feed assist (legacy: 700ms)
            self.controller.reactor.pause(self.controller.reactor.monotonic() + 0.7)

            logging.info(f'ToolCommands: Enabled feed assist for tool {tool}')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to enable feed assist: {e}')

    def _disable_feed_assist(self, tool):
        """
        Disable feed assist for specified tool.

        Matches legacy BunnyACE behavior (line 636): only disables specific gate.

        Args:
            tool: Tool (gate) number
        """
        try:
            device, local_gate = self.device_manager.get_device_for_gate(tool)

            def callback(response):
                if 'code' in response and response['code'] != 0:
                    logging.warning(f"ACE Error disabling feed assist: {response.get('msg', 'Unknown error')}")

            logging.info(f'ToolCommands: Disabling feed assist for tool {tool} (device {device.device_id}, local gate {local_gate})')
            device.stop_feed_assist(local_gate, callback)
            device.wait_ready()

            # Update controller state
            if tool < len(self.controller.gate_feed_assist):
                self.controller.gate_feed_assist[tool] = False

            # Legacy BunnyACE uses 300ms delay after disable (line 646)
            logging.info(f'ToolCommands: Starting 300ms dwell after disabling feed assist')
            self.controller.reactor.pause(self.controller.reactor.monotonic() + 0.3)
            logging.info(f'ToolCommands: Completed dwell, feed assist disabled for tool {tool}')

        except ValueError as e:
            logging.error(f'ToolCommands: Failed to disable feed assist: {e}')
