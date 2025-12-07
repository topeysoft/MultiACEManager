"""
Main controller for ACE Pro multi-material system.
Orchestrates tool changes, manages sensors, and coordinates multiple devices.
"""

import logging

from .device import AceDeviceManager
from .sensors import MmuRunoutHelper
from .exceptions import AceException
from .commands import ToolCommands, ConfigCommands, StatusCommands, DryerCommands


class AceController:
    """
    Main controller for ACE Pro multi-material system.

    Responsibilities:
    - Tool change orchestration (across multiple devices)
    - Sensor management (shared extruder/toolhead sensors)
    - G-code command registration
    - Filament parking/unloading sequences
    - Endless spool logic
    - Save variables integration

    Uses:
    - AceDeviceManager for device pool management
    - AceDevice for hardware communication
    - MmuRunoutHelper for sensor handling
    """

    VARS_ACE_REVISION = 'ace__revision'

    def __init__(self, config):
        """
        Initialize ACE controller.

        Args:
            config: Klipper configuration object
        """
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()

        # Save variables for persistence
        self.save_variables = self.printer.lookup_object('save_variables', None)
        if self.save_variables:
            revision_var = self.save_variables.allVariables.get(self.VARS_ACE_REVISION, None)
            if revision_var is None:
                config.error("ACE variables not found in [save_variables]. "
                             "Add this line to your variables file: ace__revision: 1")
        else:
            config.error("Missing [save_variables] section in config. "
                         "Add to printer.cfg:\n[save_variables]\nfilename: ~/printer_data/config/variables.cfg")

        # Tool change configuration
        self.feed_speed = config.getint('feed_speed', 50)
        self.retract_speed = config.getint('retract_speed', 50)
        self.toolchange_retract_length = config.getint('toolchange_retract_length', 100)
        self.toolchange_feed_length = config.getint('toolchange_feed_length', 100)
        self.toolchange_retract_for_cut = config.getint('toolchange_retract_for_cut', 5)  # Small retract before tip cut to prevent oozing
        self.toolhead_homing_max = config.getint('toolhead_homing_max', 100)
        self.toolhead_homing_speed = config.getint('toolhead_homing_speed', 10)
        self.extruder_move_speed = config.getint('extruder_move_speed', 10)
        self.toolhead_sensor_to_nozzle_length = config.getint('toolhead_sensor_to_nozzle', 0)
        self.poop_macros = config.get('poop_macros', '_POOP')
        self.cut_macros = config.get('cut_macros', '_CUT_TIP')
        self.error_macros = config.get('error_macros', None)

        # Connection and device configuration
        self.baud = config.getint('baud', 115200)
        self.connect_retry_delay = config.getfloat('connect_retry_delay', 1.0)
        self.connect_retry_max = config.getint('connect_retry_max', 10)
        self.max_dryer_temperature = config.getint('max_dryer_temperature', 55)

        # Logging configuration
        log_level_str = config.get('log_level', 'INFO').upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logging.getLogger().setLevel(log_level)

        # Auto-registration of T macros
        self.auto_register_t_macros = config.getboolean('auto_register_t_macros', False)

        # Create device manager (handles 0-4 ACE devices)
        # Pass connection parameters to device manager
        self.device_manager = AceDeviceManager(
            self.printer,
            config,
            connect_retry_delay=self.connect_retry_delay,
            connect_retry_max=self.connect_retry_max
        )

        # Sensors (shared across all devices)
        self.extruder_sensor = None
        self.toolhead_sensor = None
        self.endstops = {}

        # Sensor configuration
        extruder_sensor_pin = config.get('extruder_sensor_pin', None)
        toolhead_sensor_pin = config.get('toolhead_sensor_pin', None)

        if extruder_sensor_pin:
            self.extruder_sensor = self._create_sensor(config, extruder_sensor_pin, "extruder_sensor", self._extruder_sensor_handler)
        if toolhead_sensor_pin:
            self.toolhead_sensor = self._create_sensor(config, toolhead_sensor_pin, "toolhead_sensor", None)

        # Current state
        self.current_tool = -1
        self.toolhead = None

        # Per-gate feed assist state (tracked per gate)
        # Initialize based on total_gates from device manager
        # Default to True - feed assist enabled by default for all gates
        self.gate_feed_assist = [True] * self.device_manager.total_gates

        # Feed retry state (for handling feed timeout retries)
        self.feed_retry_state = None

        # Command modules
        self.tool_commands = None
        self.config_commands = None
        self.status_commands = None
        self.dryer_commands = None

        # Register event handlers
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:disconnect', self._handle_disconnect)

        # Register G-code commands (after klippy:ready)
        self.printer.register_event_handler('klippy:ready', self._register_commands)

        logging.info(f"AceController: Initialized with {self.device_manager.total_gates} total gates")

    def _handle_ready(self):
        """Handle Klipper ready event"""
        self.toolhead = self.printer.lookup_object('toolhead')
        self.current_tool = int(self.save_variables.allVariables.get('ace_current_index', -1))

        # Connect all devices
        self.device_manager.connect_all()

        logging.info('AceController: Ready')

    def _enable_all_feed_assist(self):
        """
        Enable feed assist on all gates after devices are connected.
        This is called after command registration to ensure tool_commands is available.
        """
        if not self.tool_commands:
            logging.warning('AceController: Cannot enable feed assist - tool_commands not initialized')
            return

        logging.info('AceController: Enabling feed assist on all gates by default')

        for gate in range(self.device_manager.total_gates):
            try:
                self.tool_commands._enable_feed_assist(gate)
            except Exception as e:
                logging.warning(f'AceController: Failed to enable feed assist on gate {gate}: {e}')

        logging.info(f'AceController: Feed assist enabled on {self.device_manager.total_gates} gates')

    def _handle_disconnect(self):
        """Handle Klipper disconnect event"""
        self.device_manager.disconnect_all()
        logging.info('AceController: Disconnected')

    def _create_sensor(self, config, pin, name, handler):
        """
        Create a filament sensor.

        Args:
            config: Klipper configuration object
            pin: MCU pin for sensor
            name: Sensor name
            handler: Optional event handler callback
        """
        section = f"filament_switch_sensor {name}"
        logging.info(f"AceController: Creating sensor '{name}' on pin '{pin}'")

        # Add sensor section to config dynamically
        config.fileconfig.add_section(section)
        config.fileconfig.set(section, "switch_pin", pin)
        config.fileconfig.set(section, "pause_on_runout", "False")

        # Load the actual Klipper filament_switch_sensor object
        fs = self.printer.load_object(config, section)

        # Create custom runout helper for ACE-specific behavior
        ro_helper = MmuRunoutHelper(
            self.printer, name, 0.1, '', '', '',
            False, handler, pin
        )

        # Replace the sensor's runout helper with our custom one
        fs.runout_helper = ro_helper
        fs.get_status = ro_helper.get_status

        # Add dummy QUERY_PROBE handler to prevent Mainsail errors
        # (Mainsail queries all objects, including non-probe sensors)
        def dummy_query_probe(gcmd):
            gcmd.respond_info(f"Sensor {name} is a filament sensor, not a probe")
        fs.cmd_QUERY_PROBE = dummy_query_probe

        # Set up endstop pin for multi-use (shared with sensor)
        ppins = self.printer.lookup_object('pins')
        try:
            pin_params = ppins.parse_pin(pin, True, True)
            share_name = f"{pin_params['chip_name']}:{pin_params['pin']}"
            ppins.allow_multi_use_pin(share_name)
            mcu_endstop = ppins.setup_pin('endstop', pin)
            logging.info(f"AceController: Successfully set up endstop for '{name}'")
        except Exception as e:
            logging.error(f"AceController: Failed to setup pin '{pin}' for sensor '{name}': {e}")
            raise

        # Store endstop
        self.endstops[name] = mcu_endstop

        # Register with query_endstops
        query_endstops = self.printer.load_object(config, "query_endstops")
        query_endstops.register_endstop(mcu_endstop, share_name)

        logging.info(f"AceController: ✓ Registered sensor '{name}'")

        return fs

    def _extruder_sensor_handler(self, eventtime, is_filament_present, runout_helper):
        """
        Handle extruder sensor events (runout detection).

        Args:
            eventtime: Event timestamp
            is_filament_present: Whether filament is detected
            runout_helper: The sensor helper instance
        """
        current_index = self.save_variables.allVariables.get('ace_current_index', -1)

        # Check if printing
        now = self.reactor.monotonic()
        print_stats = self.printer.lookup_object("print_stats", None)
        if print_stats is not None:
            is_printing = print_stats.get_status(now)["state"] == "printing"
        else:
            is_printing = self.printer.lookup_object("idle_timeout").get_status(now)["state"] == "Printing"

        # Handle runout during print
        if (not is_filament_present) and current_index >= 0 and is_printing:
            # Get device and local gate for current tool
            try:
                device, local_gate = self.device_manager.get_device_for_gate(current_index)
                device_status = device.get_status()

                # Check if gate is empty
                if device_status['active_gate'][local_gate] == 'empty':
                    logging.warning(f"AceController: Filament runout detected on gate {current_index}")

                    # Mark as unloaded
                    self.save_variables.allVariables['ace_current_index'] = -1
                    self.save_variable('ace_current_index', -1, True)

                    # Pause print
                    pause_resume = self.printer.lookup_object('pause_resume')
                    pause_resume.send_pause_command()

                    # Check for endless spool
                    if self.save_variables.allVariables.get('ace_endless_spool', False):
                        logging.info('AceController: Endless spool enabled, searching for replacement')

                        # Get material configuration
                        ace_material = self.save_variables.allVariables.get('ace_gate_type', [''] * self.device_manager.total_gates)

                        # Ensure material array matches total gates
                        while len(ace_material) < self.device_manager.total_gates:
                            ace_material.append('')

                        # Get current material type
                        runout_material = ace_material[current_index] if current_index < len(ace_material) else ''

                        # Get all gate statuses from device manager
                        aggregated_status = self.device_manager.get_aggregated_status()
                        all_slots = aggregated_status.get('slots', [])

                        # Filter available spools: not empty, same material, not the runout gate
                        spools = list(filter(
                            lambda x: x['status'] != 'empty'
                                and x['index'] != current_index
                                and (x['index'] < len(ace_material) and ace_material[x['index']] == runout_material),
                            all_slots
                        ))

                        if len(spools) == 0:
                            logging.warning("AceController: No suitable spools for endless spool - no matching material or all empty")
                            self.gcode.respond_info(f'Filament runout on T{current_index}! No matching spools available (material: {runout_material})')
                        else:
                            replacement_gate = spools[0]['index']
                            logging.info(f'AceController: Endless spool - switching from T{current_index} to T{replacement_gate} (material: {runout_material})')
                            self.gcode.respond_info(f'Endless spool: T{current_index} empty, switching to T{replacement_gate}')

                            # Execute tool change
                            self.gcode.run_script_from_command(f'ACE_CHANGE_TOOL TOOL={replacement_gate}')

                            # Resume print
                            pause_resume.send_resume_command()
                    else:
                        self.gcode.respond_info('Filament runout! Endless spool disabled')
            except Exception as e:
                logging.error(f"AceController: Error handling runout: {e}")
                import traceback
                traceback.print_exc()

    def _register_commands(self):
        """Register G-code commands via command modules"""
        # Create command modules
        self.tool_commands = ToolCommands(self)
        self.config_commands = ConfigCommands(self)
        self.status_commands = StatusCommands(self)
        self.dryer_commands = DryerCommands(self)

        # Register all commands
        self.tool_commands.register()
        self.config_commands.register()
        self.status_commands.register()
        self.dryer_commands.register()

        logging.info("AceController: All G-code commands registered")

        # Schedule feed assist enablement after devices have time to connect
        # Use a delayed timer to ensure devices are connected and ready
        self.reactor.register_callback(self._delayed_feed_assist_enable)

    def _delayed_feed_assist_enable(self, eventtime):
        """
        Delayed callback to enable feed assist after device connection.
        Called a few seconds after startup to allow devices to connect.
        """
        # Wait a bit longer for devices to fully connect
        import time
        time.sleep(3.0)
        self._enable_all_feed_assist()

    def save_variable(self, variable, value, write=False):
        """Save variable to persistent storage"""
        self.save_variables.allVariables[variable] = value
        if write:
            self.write_variables()

    def write_variables(self):
        """Write variables to file"""
        mmu_vars_revision = self.save_variables.allVariables.get(self.VARS_ACE_REVISION, 0) + 1
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=%d" % (self.VARS_ACE_REVISION, mmu_vars_revision))

    # ========================================================================
    # Helper Methods (used by command modules)
    # ========================================================================

    def query_sensor_pin(self, sensor):
        """
        Query sensor pin state directly from MCU.

        This bypasses the cached button callback state and reads the pin directly,
        ensuring real-time sensor detection during tool changes.

        Args:
            sensor: Sensor object (extruder_sensor or toolhead_sensor)

        Returns:
            bool: True if filament is detected (pin triggered), False otherwise
        """
        if sensor is None:
            return False

        # Get the endstop for this sensor
        endstop = self.endstops.get(sensor.runout_helper.name)
        if endstop is None:
            logging.warning(f"AceController: No endstop found for sensor {sensor.runout_helper.name}, falling back to cached state")
            return sensor.runout_helper.filament_present

        # Query the endstop pin state directly
        # This returns the current pin state from the MCU
        print_time = self.toolhead.get_last_move_time()
        pin_value = endstop.query_endstop(print_time)

        # Pin logic: typically sensor is triggered when pin goes high (filament present)
        # But this depends on the pin configuration (^ for pullup, ! for invert)
        # The button handler passes state directly, so we match that behavior
        return bool(pin_value)


    def get_status(self, eventtime=None):
        """
        Get status for Klipper status reporting.

        Returns:
            Status dictionary
        """
        device_status = self.device_manager.get_aggregated_status()

        # Get saved gate configuration
        gate_colors = self.save_variables.allVariables.get('ace_gate_color', ['FFFFFF'] * self.device_manager.total_gates)
        gate_materials = self.save_variables.allVariables.get('ace_gate_type', [''] * self.device_manager.total_gates)
        gate_temps = self.save_variables.allVariables.get('ace_gate_temp', [230] * self.device_manager.total_gates)

        # Ensure arrays match total gates
        while len(gate_colors) < self.device_manager.total_gates:
            gate_colors.append('FFFFFF')
        while len(gate_materials) < self.device_manager.total_gates:
            gate_materials.append('')
        while len(gate_temps) < self.device_manager.total_gates:
            gate_temps.append(230)

        return {
            'total_gates': self.device_manager.total_gates,
            'num_devices': device_status['num_devices'],
            'selected_gate': self.current_tool,
            'active_gate': device_status['active_gate'],
            'gate_color': gate_colors[:self.device_manager.total_gates],
            'gate_material': gate_materials[:self.device_manager.total_gates],
            'gate_temp': gate_temps[:self.device_manager.total_gates],
            'spool_id': list(range(1, self.device_manager.total_gates + 1)),
            'endless_spool': bool(self.save_variables.allVariables.get('ace_endless_spool', False)),
            'gate_feed_assist': self.gate_feed_assist[:self.device_manager.total_gates],
            'devices': device_status['devices']
        }
