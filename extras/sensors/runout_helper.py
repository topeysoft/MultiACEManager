"""
Filament runout sensor helper for ACE Pro system.
Handles filament detection events and triggers appropriate actions.
"""

import logging


class MmuRunoutHelper:
    """
    Helper class for managing filament sensor events.

    Handles:
    - Filament insert/remove detection
    - Runout detection during printing
    - G-code execution on sensor events
    - Sensor enable/disable state
    """

    def __init__(self, printer, name, event_delay, insert_gcode, remove_gcode, runout_gcode, insert_remove_in_print,
                 button_handler, switch_pin):
        """
        Initialize filament sensor helper.

        Args:
            printer: Klipper printer object
            name: Sensor name (e.g., 'extruder_sensor')
            event_delay: Minimum time between events (seconds)
            insert_gcode: G-code to run on filament insert
            remove_gcode: G-code to run on filament remove
            runout_gcode: G-code to run on filament runout during print
            insert_remove_in_print: Whether to handle insert/remove during printing
            button_handler: Optional handler for button feedback
            switch_pin: MCU pin for the sensor
        """
        self.printer, self.name = printer, name
        self.insert_gcode, self.remove_gcode, self.runout_gcode = insert_gcode, remove_gcode, runout_gcode
        self.insert_remove_in_print = insert_remove_in_print
        self.button_handler = button_handler
        self.switch_pin = switch_pin
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')

        self.min_event_systime = self.reactor.NEVER
        self.event_delay = event_delay  # Time between generated events
        self.filament_present = False
        self.sensor_enabled = True
        self.runout_suspended = None
        self.button_handler_suspended = False

        self.printer.register_event_handler("klippy:ready", self._handle_ready)

        # Replace previous runout_helper mux commands with ours
        prev = self.gcode.mux_commands.get("QUERY_FILAMENT_SENSOR")
        if prev is not None:
            _, prev_values = prev
            prev_values[self.name] = self.cmd_QUERY_FILAMENT_SENSOR
        else:
            # First sensor - register the mux command
            self.gcode.register_mux_command("QUERY_FILAMENT_SENSOR", "SENSOR", self.name,
                                           self.cmd_QUERY_FILAMENT_SENSOR,
                                           desc=self.cmd_QUERY_FILAMENT_SENSOR_help)

        prev = self.gcode.mux_commands.get("SET_FILAMENT_SENSOR")
        if prev is not None:
            _, prev_values = prev
            prev_values[self.name] = self.cmd_SET_FILAMENT_SENSOR
        else:
            # First sensor - register the mux command
            self.gcode.register_mux_command("SET_FILAMENT_SENSOR", "SENSOR", self.name,
                                           self.cmd_SET_FILAMENT_SENSOR,
                                           desc=self.cmd_SET_FILAMENT_SENSOR_help)

    def _handle_ready(self):
        """Handle klippy ready event - wait before processing first events"""
        self.min_event_systime = self.reactor.monotonic() + 2.  # Time to wait before first events are processed

    def _insert_event_handler(self, eventtime):
        """Execute insert G-code"""
        self._exec_gcode("%s EVENTTIME=%s" % (self.insert_gcode, eventtime))

    def _remove_event_handler(self, eventtime):
        """Execute remove G-code"""
        self._exec_gcode("%s EVENTTIME=%s" % (self.remove_gcode, eventtime))

    def _runout_event_handler(self, eventtime):
        """Execute runout G-code and pause print"""
        # Pausing from inside an event requires that the pause portion of pause_resume execute immediately.
        pause_resume = self.printer.lookup_object('pause_resume')
        pause_resume.send_pause_command()
        self._exec_gcode("%s EVENTTIME=%s" % (self.runout_gcode, eventtime))

    def _exec_gcode(self, command):
        """Execute G-code command and update event time"""
        if command:
            try:
                self.gcode.run_script(command)
            except Exception:
                logging.exception("MMU: Error running mmu sensor handler: `%s`" % command)
        self.min_event_systime = self.reactor.monotonic() + self.event_delay

    def note_filament_present(self, *args):
        """
        Update filament present state.

        Args:
            *args: Either (is_present,) or (eventtime, is_present)
        """
        if len(args) == 1:
            eventtime = self.reactor.monotonic()
            is_filament_present = args[0]
        else:
            eventtime = args[0]
            is_filament_present = args[1]

        # Button handlers are used for sync feedback state switches
        if self.button_handler and not self.button_handler_suspended:
            self.button_handler(eventtime, is_filament_present, self)

        if is_filament_present == self.filament_present:
            return

        # Log state change for debugging
        logging.info(f"ACE: Sensor {self.name} state changed: {'present' if is_filament_present else 'not present'}")
        self.filament_present = is_filament_present

        # Don't handle too early or if disabled
        if eventtime >= self.min_event_systime and self.sensor_enabled:
            self._process_state_change(eventtime, is_filament_present)
        else:
            logging.debug(f"ACE: Sensor {self.name} event ignored - eventtime: {eventtime}, min_event: {self.min_event_systime}, enabled: {self.sensor_enabled}")

    def _process_state_change(self, eventtime, is_filament_present):
        """Process filament state change and trigger appropriate actions"""
        # Determine "printing" status
        now = self.reactor.monotonic()
        print_stats = self.printer.lookup_object("print_stats", None)
        if print_stats is not None:
            is_printing = print_stats.get_status(now)["state"] == "printing"
        else:
            is_printing = self.printer.lookup_object("idle_timeout").get_status(now)["state"] == "Printing"

        if is_filament_present and self.insert_gcode:  # Insert detected
            if not is_printing or (is_printing and self.insert_remove_in_print):
                self.min_event_systime = self.reactor.NEVER
                # logging.info("MMU: filament sensor %s: insert event detected, Eventtime %.2f" % (self.name, eventtime))
                self.reactor.register_callback(lambda reh: self._insert_event_handler(eventtime))

        else:  # Remove or Runout detected
            self.min_event_systime = self.reactor.NEVER
            if is_printing and self.runout_suspended is False and self.runout_gcode:
                # logging.info("MMU: filament sensor %s: runout event detected, Eventtime %.2f" % (self.name, eventtime))
                self.reactor.register_callback(lambda reh: self._runout_event_handler(eventtime))
            elif self.remove_gcode and (not is_printing or self.insert_remove_in_print):
                # Just a "remove" event
                # logging.info("MMU: filament sensor %s: remove event detected, Eventtime %.2f" % (self.name, eventtime))
                self.reactor.register_callback(lambda reh: self._remove_event_handler(eventtime))

    def enable_runout(self, restore):
        """Enable or disable runout detection"""
        self.runout_suspended = not restore

    def enable_button_feedback(self, restore):
        """Enable or disable button feedback"""
        self.button_handler_suspended = not restore

    def get_status(self, eventtime):
        """Get sensor status for Klipper status reporting"""
        return {
            "filament_detected": bool(self.filament_present),
            "enabled": bool(self.sensor_enabled),
            "runout_suspended": bool(self.runout_suspended),
        }

    cmd_QUERY_FILAMENT_SENSOR_help = "Query the status of the Filament Sensor"

    def cmd_QUERY_FILAMENT_SENSOR(self, gcmd):
        """G-code command: QUERY_FILAMENT_SENSOR SENSOR=<name>"""
        if self.filament_present:
            msg = "MMU Sensor %s: filament detected" % (self.name)
        else:
            msg = "MMU Sensor %s: filament not detected" % (self.name)
        gcmd.respond_info(msg)

    cmd_SET_FILAMENT_SENSOR_help = "Sets the filament sensor on/off"

    def cmd_SET_FILAMENT_SENSOR(self, gcmd):
        """G-code command: SET_FILAMENT_SENSOR SENSOR=<name> ENABLE=<0|1>"""
        self.sensor_enabled = bool(gcmd.get_int("ENABLE", 1))
