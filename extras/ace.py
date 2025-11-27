import serial, threading, time, logging, json, struct, queue, traceback, re, os, subprocess
from serial import SerialException
import serial.tools.list_ports
from typing import Optional, Dict, List, Callable, Any, Tuple

# Protocol Constants
PROTOCOL_HEAD_BYTES = bytes([0xFF, 0xAA])
PROTOCOL_TAIL_BYTE = 0xFE
PROTOCOL_MIN_PACKET_SIZE = 7
CRC_INIT_VALUE = 0xFFFF

# Timing Constants
DEFAULT_EVENT_DELAY = 0.1
READY_WAIT_DELAY = 2.0
CONNECT_RETRY_DELAY = 1.0
READER_POLL_INTERVAL = 0.2
WRITER_POLL_INTERVAL = 0.5
SENSOR_POLL_INTERVAL = 0.1
REQUEST_TIMEOUT = 2.0
FEED_ASSIST_DELAY = 0.7
FEED_ASSIST_DISABLE_DELAY = 0.3

# ACE Device Constants
DEFAULT_NUM_GATES = 4
GATES_PER_ACE = 4
DEFAULT_BAUD_RATE = 115200
DEFAULT_MAX_DRYER_TEMP = 55
DEFAULT_FEED_SPEED = 50
DEFAULT_RETRACT_SPEED = 50
DEFAULT_EXTRUDER_SPEED = 10
DEFAULT_TOOLHEAD_HOMING_SPEED = 10
DEFAULT_TOOLCHANGE_RETRACT_LENGTH = 100
DEFAULT_TOOLCHANGE_FEED_LENGTH = 100
DEFAULT_TOOLHEAD_HOMING_MAX = 100

# Request ID bounds
MAX_REQUEST_ID = 300000

# Default colors and materials
DEFAULT_COLOR = 'FFFFFF'
DEFAULT_MATERIAL = ''
DEFAULT_TEMP = 230


class MmuRunoutHelper:
    def __init__(self, printer, name, event_delay, insert_gcode, remove_gcode, runout_gcode, insert_remove_in_print,
                 button_handler, switch_pin):

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
        self.min_event_systime = self.reactor.monotonic() + 2.  # Time to wait before first events are processed

    def _insert_event_handler(self, eventtime):
        self._exec_gcode("%s EVENTTIME=%s" % (self.insert_gcode, eventtime))

    def _remove_event_handler(self, eventtime):
        self._exec_gcode("%s EVENTTIME=%s" % (self.remove_gcode, eventtime))

    def _runout_event_handler(self, eventtime):
        # Pausing from inside an event requires that the pause portion of pause_resume execute immediately.
        pause_resume = self.printer.lookup_object('pause_resume')
        pause_resume.send_pause_command()
        self._exec_gcode("%s EVENTTIME=%s" % (self.runout_gcode, eventtime))

    def _exec_gcode(self, command):
        if command:
            try:
                self.gcode.run_script(command)
            except Exception:
                logging.exception("MMU: Error running mmu sensor handler: `%s`" % command)
        self.min_event_systime = self.reactor.monotonic() + self.event_delay

    def note_filament_present(self, *args):
        if len(args) == 1:
            eventtime = self.reactor.monotonic()
            is_filament_present = args[0]
        else:
            eventtime = args[0]
            is_filament_present = args[1]

        # Button handlers are used for sync feedback state switches
        if self.button_handler and not self.button_handler_suspended:
            self.button_handler(eventtime, is_filament_present, self)

        if is_filament_present == self.filament_present: return
        self.filament_present = is_filament_present

        # Don't handle too early or if disabled
        if eventtime >= self.min_event_systime and self.sensor_enabled:
            self._process_state_change(eventtime, is_filament_present)

    def _process_state_change(self, eventtime, is_filament_present):
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
        self.runout_suspended = not restore

    def enable_button_feedback(self, restore):
        self.button_handler_suspended = not restore

    def get_status(self, eventtime):
        return {
            "filament_detected": bool(self.filament_present),
            "enabled": bool(self.sensor_enabled),
            "runout_suspended": bool(self.runout_suspended),
        }

    cmd_QUERY_FILAMENT_SENSOR_help = "Query the status of the Filament Sensor"

    def cmd_QUERY_FILAMENT_SENSOR(self, gcmd):
        if self.filament_present:
            msg = "MMU Sensor %s: filament detected" % (self.name)
        else:
            msg = "MMU Sensor %s: filament not detected" % (self.name)
        gcmd.respond_info(msg)

    cmd_SET_FILAMENT_SENSOR_help = "Sets the filament sensor on/off"

    def cmd_SET_FILAMENT_SENSOR(self, gcmd):
        self.sensor_enabled = bool(gcmd.get_int("ENABLE", 1))

class AceException(Exception):
    pass


class AceDeviceDiscovery:
    """Handles auto-discovery and enumeration of ACE devices"""

    ACE_VID = 0x28E9  # GDMicroelectronics vendor ID
    ACE_PID = 0x018A  # ACE product ID
    ACE_MANUFACTURER = "GDMicroelectronics"
    ACE_PRODUCT_NAME = "ACE"

    @staticmethod
    def find_ace_devices():
        """
        Scan all USB serial ports and identify ACE devices
        Returns: List of dicts with port info and device details
        """
        ace_devices = []
        ports = serial.tools.list_ports.comports()

        for port in ports:
            # Method 1: VID/PID matching (most reliable)
            if port.vid == AceDeviceDiscovery.ACE_VID:
                ace_devices.append({
                    'port': port.device,
                    'hwid': port.hwid,
                    'serial_number': port.serial_number,
                    'manufacturer': port.manufacturer,
                    'product': port.product,
                    'vid': port.vid,
                    'pid': port.pid,
                    'location': port.location  # USB hub location for stable ordering
                })
            # Method 2: Manufacturer/Product string matching (fallback)
            elif (port.manufacturer and AceDeviceDiscovery.ACE_MANUFACTURER.upper() in str(port.manufacturer).upper()) or \
                 (port.product and AceDeviceDiscovery.ACE_PRODUCT_NAME.upper() in str(port.product).upper()):
                ace_devices.append({
                    'port': port.device,
                    'hwid': port.hwid,
                    'serial_number': port.serial_number,
                    'manufacturer': port.manufacturer,
                    'product': port.product,
                    'vid': port.vid,
                    'pid': port.pid,
                    'location': port.location
                })

        # Sort by USB location for deterministic ordering
        ace_devices.sort(key=lambda x: x.get('location', '') or '')

        return ace_devices

    @staticmethod
    def probe_ace_device(port, baud=115200, timeout=2.0, usb_location=None):
        """
        Connect to a port and verify it's an ACE device
        Args:
            port: Serial port path
            baud: Baud rate (default 115200)
            timeout: Serial timeout (default 2.0s)
            usb_location: USB bus-port location (e.g., "1-1.2") for device_id fallback
        Returns: Device info dict or None if not ACE
        """
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=timeout,
                write_timeout=timeout
            )

            # Send get_info request using ACE protocol
            request = {"id": 1, "method": "get_info"}

            # Build protocol packet
            payload = json.dumps(request).encode('utf-8')
            data = PROTOCOL_HEAD_BYTES
            data += struct.pack('@H', len(payload))
            data += payload

            # Calculate CRC
            crc_value = CRC_INIT_VALUE
            for byte in payload:
                byte_data = byte
                byte_data ^= crc_value & 0xff
                byte_data ^= (byte_data & 0x0f) << 4
                crc_value = ((byte_data << 8) | (crc_value >> 8)) ^ (byte_data >> 4) ^ (byte_data << 3)

            data += struct.pack('@H', crc_value)
            data += bytes([PROTOCOL_TAIL_BYTE])

            ser.write(data)
            time.sleep(0.5)  # Wait for response

            # Try to read response
            if ser.in_waiting > 0:
                response_data = ser.read(ser.in_waiting)

                # Parse response
                if len(response_data) >= PROTOCOL_MIN_PACKET_SIZE and response_data[0:2] == PROTOCOL_HEAD_BYTES:
                    payload_len = struct.unpack('<H', response_data[2:4])[0]
                    if len(response_data) >= 4 + payload_len:
                        response_payload = response_data[4:4 + payload_len]

                        try:
                            response_json = json.loads(response_payload.decode('utf-8'))
                            if 'result' in response_json:
                                result = response_json['result']
                                # Add USB location to result for device_id generation
                                if usb_location:
                                    result['usb_location'] = usb_location
                                device_id = AceDeviceDiscovery._generate_device_id(result)

                                ser.close()
                                return {
                                    'device_id': device_id,
                                    'model': result.get('model', 'Unknown'),
                                    'firmware': result.get('firmware', 'Unknown'),
                                    'serial_number': result.get('serial_number', None),
                                    'mac_address': result.get('mac_address', None),
                                    'num_gates': 4  # Default, can be detected from slots
                                }
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            pass

            ser.close()
            return None

        except Exception as e:
            logging.warning(f"Failed to probe {port}: {e}")
            return None

    @staticmethod
    def _generate_device_id(device_info):
        """
        Generate device ID based on USB port location.
        This ensures the same physical USB port always maps to the same device ID,
        making gate assignments stable and predictable across reboots.

        Format: hub_1_port_3 (readable) from USB location like "1-1.3"
        """
        import hashlib

        # Always use USB location as the primary device ID
        if 'usb_location' in device_info and device_info['usb_location']:
            # USB location like "1-1.2" is stable as long as device stays in same port
            # Convert to readable format: "1-1.2" → "hub_1_port_2"
            usb_loc = device_info['usb_location']

            # Parse USB location format (e.g., "1-1.2" means bus 1, port 1.2)
            # We'll create a readable name based on the port path
            parts = usb_loc.split('-')
            if len(parts) >= 2:
                # Get the port path (everything after the bus number)
                port_path = parts[1].replace('.', '_')
                return f"hub_{parts[0]}_port_{port_path}"
            else:
                # Fallback for simple format
                usb_loc_clean = usb_loc.replace('.', '_').replace('-', '_')
                return f"usb_{usb_loc_clean}"

        # Fallback: MAC address (if firmware provides it)
        if 'mac_address' in device_info and device_info['mac_address']:
            mac = device_info['mac_address'].replace(':', '')
            logging.info(f"ACE: Using MAC address for device_id (USB location not available)")
            return f"mac_{mac}"

        # Fallback: Serial number (if firmware provides it)
        if 'serial_number' in device_info and device_info['serial_number']:
            logging.info(f"ACE: Using serial number for device_id (USB location not available)")
            return f"sn_{device_info['serial_number']}"

        # Last resort: Hash of firmware + model (NOT recommended - not unique across identical devices)
        unique_str = f"{device_info.get('model', '')}_{device_info.get('firmware', '')}"
        hash_val = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        logging.warning(f"ACE: Using firmware hash for device_id (not unique!). Consider using USB hub for stable port locations.")
        return f"fw_{hash_val}"


class AceDeviceMapper:
    """
    Manages persistent device properties mapped by device ID (USB location).
    Gate offsets are dynamically assigned at runtime based on currently connected devices.
    Device properties (colors, materials, temps) persist with the device regardless of gate assignment.
    """

    def __init__(self, config_path):
        self.config_path = config_path
        self.device_map = {}  # device_id -> {port, usb_location, properties, last_seen, last_gate_offset}
        self.load()

    def load(self):
        """Load device map and properties from file"""
        import configparser
        import json

        if not os.path.exists(self.config_path):
            return

        parser = configparser.ConfigParser()
        parser.read(self.config_path)

        # Load device metadata from main section (backward compatible)
        if parser.has_section('ace_device_map'):
            for device_id, value in parser.items('ace_device_map'):
                if device_id.startswith('#'):
                    continue
                parts = [p.strip() for p in value.split(',')]
                if len(parts) >= 2:
                    self.device_map[device_id] = {
                        'port': parts[0],
                        'usb_location': parts[3] if len(parts) > 3 else '',
                        'last_seen': int(parts[2]) if len(parts) > 2 else 0,
                        'last_gate_offset': int(parts[1]) if len(parts) > 1 else 0,  # Informational only
                        'properties': {}
                    }

        # Load device-specific properties from individual sections
        for section in parser.sections():
            if section.startswith('device:'):
                device_id = section[7:]  # Remove 'device:' prefix
                if device_id not in self.device_map:
                    self.device_map[device_id] = {
                        'port': '',
                        'usb_location': '',
                        'last_seen': 0,
                        'last_gate_offset': 0,
                        'properties': {}
                    }

                # Load properties
                props = {}
                for key, value in parser.items(section):
                    try:
                        # Try to parse as JSON for lists
                        props[key] = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        # Store as string if not JSON
                        props[key] = value

                self.device_map[device_id]['properties'] = props

    def save(self):
        """Save device map and properties to file"""
        import configparser
        import json

        parser = configparser.ConfigParser()

        # Save main device mapping section
        parser.add_section('ace_device_map')
        for device_id, info in sorted(self.device_map.items()):
            value = f"{info['port']}, {info['last_gate_offset']}, {int(time.time())}, {info.get('usb_location', '')}"
            parser.set('ace_device_map', device_id, value)

        # Save device-specific properties in separate sections
        for device_id, info in sorted(self.device_map.items()):
            if info.get('properties'):
                section_name = f'device:{device_id}'
                parser.add_section(section_name)
                for prop_key, prop_value in info['properties'].items():
                    # Serialize lists/dicts as JSON
                    if isinstance(prop_value, (list, dict)):
                        value_str = json.dumps(prop_value)
                    else:
                        value_str = str(prop_value)
                    parser.set(section_name, prop_key, value_str)

        # Write with header comment
        with open(self.config_path, 'w') as f:
            f.write('# Auto-generated by ACE Manager - DO NOT EDIT MANUALLY\n')
            f.write('# This file stores device properties by USB port location\n')
            f.write('# Gate offsets are dynamically assigned based on currently connected devices\n')
            f.write('# Device properties (colors, materials, temps) persist with the device\n\n')
            parser.write(f)

    def update_device(self, device_id, port, usb_location=None, current_gate_offset=None):
        """Update or add a device mapping"""
        if device_id not in self.device_map:
            self.device_map[device_id] = {
                'port': port,
                'usb_location': usb_location or '',
                'last_seen': int(time.time()),
                'last_gate_offset': current_gate_offset if current_gate_offset is not None else 0,
                'properties': {}
            }
        else:
            self.device_map[device_id]['port'] = port
            self.device_map[device_id]['usb_location'] = usb_location or self.device_map[device_id].get('usb_location', '')
            self.device_map[device_id]['last_seen'] = int(time.time())
            if current_gate_offset is not None:
                self.device_map[device_id]['last_gate_offset'] = current_gate_offset

    def get_device_properties(self, device_id):
        """Get properties for a device"""
        return self.device_map.get(device_id, {}).get('properties', {})

    def update_device_properties(self, device_id, properties):
        """Update properties for a device"""
        if device_id in self.device_map:
            self.device_map[device_id]['properties'].update(properties)
        else:
            logging.warning(f"ACE Mapper: Tried to update properties for unknown device {device_id}")

    def get_device_info(self, device_id):
        """Get full device info"""
        return self.device_map.get(device_id, {})

    def get_all_devices(self):
        """Get all known devices"""
        return self.device_map.copy()

    def find_device_by_port(self, port):
        """Find device ID by current port"""
        for device_id, info in self.device_map.items():
            if info['port'] == port:
                return device_id
        return None


class BunnyAce:
    VARS_ACE_REVISION = 'ace__revision'

    def __init__(self, config):
        self._connected = False
        self._serial = None
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self._name = config.get_name()
        self._lock = threading.Lock()
        self._request_in_flight = False
        self._pending_request_id: Optional[int] = None
        self.send_time = None
        self.read_buffer = bytearray()
        if self._name.startswith('ace '):
            self._name = self._name[4:]

        self.save_variables = self.printer.lookup_object('save_variables', None)
        if self.save_variables:
            revision_var = self.save_variables.allVariables.get(self.VARS_ACE_REVISION, None)
            if revision_var is None:
                config.error("You have custom [save_variables]. "
                             "Copy the contents of ace_vars.cfg to your file and remove [save_variables] in ace.cfg")
        else:
            config.error("There is no [save_variables] in the config. Check installation guide")

        self.serial_id = config.get('serial', '/dev/ttyACM0')
        self.baud = config.getint('baud', 115200)

        # Gate offset for multi-ACE setups (e.g., second ACE has offset=4 for gates 4-7)
        self.gate_offset = config.getint('gate_offset', 0)

        extruder_sensor_pin = config.get('extruder_sensor_pin')
        toolhead_sensor_pin = config.get('toolhead_sensor_pin', None)
        self.feed_speed = config.getint('feed_speed', 50)
        self.retract_speed = config.getint('retract_speed', 50)
        self.toolchange_retract_length = config.getint('toolchange_retract_length', 100)
        self.toolchange_feed_length = config.getint('toolchange_feed_length', 100)
        self.toolhead_homing_max = config.getint('toolhead_homing_max', 100)
        self.toolhead_homing_speed = config.getint('toolhead_homing_speed', 10)
        self.extruder_move_speed = config.getint('extruder_move_speed', 10)
        self.toolhead_sensor_to_nozzle_length = config.getint('toolhead_sensor_to_nozzle', 0)
        self.poop_macros = config.get('poop_macros', '_POOP')
        self.cut_macros = config.get('cut_macros', '_CUT_TIP')

        # self.extruder_to_blade_length = config.getint('extruder_to_blade', None)

        self.max_dryer_temperature = config.getint('max_dryer_temperature', 55)

        self._callback_map = {}
        self._feed_assist_index = -1
        self._request_id = 0
        self._connection_retry_count = 0
        self.endstops = {}

        # Default data to prevent exceptions
        # num_gates will be dynamically detected from ACE firmware response
        self.num_gates = 4  # Minimum default, will be updated from get_status
        self.gate_status = ['empty'] * self.num_gates
        self._info = {
            'status': 'ready',
            'dryer_status': {
                'status': 'stop',
                'target_temp': 0,
                'duration': 0,
                'remain_time': 0
            },
            'temp': 0,
            'enable_rfid': 1,
            'fan_speed': 7000,
            'feed_assist_count': 0,
            'cont_assist_time': 0.0,
            'slots': []  # Will be populated dynamically from get_status
        }
        # Initialize with minimum 4 slots for backward compatibility
        for i in range(self.num_gates):
            self._info['slots'].append({
                'index': i,
                'status': 'empty',
                'sku': '',
                'type': '',
                'color': [0, 0, 0]
            })
        self._create_mmu_sensor(config, extruder_sensor_pin, "extruder_sensor", self.extruder_sensor_handler)
        if toolhead_sensor_pin is not None and len(toolhead_sensor_pin) >= 2:
            self._create_mmu_sensor(config, toolhead_sensor_pin, "toolhead_sensor")

        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:disconnect', self._handle_disconnect)
        # self.printer.register_event_handler('klippy:shutdown', self._handle_disconnect)

        # Only register global commands if this is a standalone ACE (not managed)
        # Managed ACEs will have their commands registered by AceManager
        self.is_managed = self._name != 'ace'  # If name is not default, it's managed

        if not self.is_managed:
            self.gcode.register_command(
                'ACE_DEBUG', self.cmd_ACE_DEBUG,
                desc='self.cmd_ACE_DEBUG_help')
            self.gcode.register_command(
                'ACE_START_DRYING', self.cmd_ACE_START_DRYING,
                desc=self.cmd_ACE_START_DRYING_help)
            self.gcode.register_command(
                'ACE_STOP_DRYING', self.cmd_ACE_STOP_DRYING,
                desc=self.cmd_ACE_STOP_DRYING_help)
            self.gcode.register_command(
                'ACE_ENABLE_FEED_ASSIST', self.cmd_ACE_ENABLE_FEED_ASSIST,
                desc=self.cmd_ACE_ENABLE_FEED_ASSIST_help)
            self.gcode.register_command(
                'ACE_DISABLE_FEED_ASSIST', self.cmd_ACE_DISABLE_FEED_ASSIST,
                desc=self.cmd_ACE_DISABLE_FEED_ASSIST_help)
            self.gcode.register_command(
                'ACE_FEED', self.cmd_ACE_FEED,
                desc=self.cmd_ACE_FEED_help)
            self.gcode.register_command(
                'ACE_RETRACT', self.cmd_ACE_RETRACT,
                desc=self.cmd_ACE_RETRACT_help)
            self.gcode.register_command(
                'ACE_CHANGE_TOOL', self.cmd_ACE_CHANGE_TOOL,
                desc=self.cmd_ACE_CHANGE_TOOL_help)
            self.gcode.register_command(
                'ACE_GATE_MAP', self.cmd_ACE_GATE_MAP,
                desc=self.cmd_ACE_GATE_MAP_help)
            self.gcode.register_command(
                'ACE_ENDLESS_SPOOL', self.cmd_ACE_ENDLESS_SPOOL,
                desc=self.cmd_ACE_ENDLESS_SPOOL_help
            )
            self.gcode.register_command(
                'ACE_GET_STATUS', self.cmd_ACE_GET_STATUS,
                desc=self.cmd_ACE_GET_STATUS_help
            )

    def _handle_ready(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        logging.info('ACE: Connecting to ' + self.serial_id)
        # We can catch timing where ACE reboots itself when no data is available from host. We're avoiding it with this hack
        self._connected = False
        self._queue = queue.Queue()
        self._main_queue = queue.Queue()
        self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)

    def _handle_disconnect(self):
        logging.info('ACE: Closing connection to ' + self.serial_id)
        self._serial.close()
        self._connected = False
        self.reactor.unregister_timer(self.writer_timer)
        self.reactor.unregister_timer(self.reader_timer)

        self._queue = None
        self._main_queue = None

    def _color_message(self, msg):
        try:
            html_msg = msg.format(
                '</span>',  # {0}
                '<span style="color:#FFFF00">',  # {1}
                '<span style="color:#90EE90">',  # {2}
                '<span style="color:#458EFF">',  # {3}
                '<b>',  # {5}
                '</b>'  # {6}
            )
        except (IndexError, KeyError, ValueError) as e:
            html_msg = msg
        return html_msg

    def log_warning(self, msg):
        c_msg = self._color_message('{1}%s{0}' % msg)
        self.gcode.respond_raw(c_msg)

    def log_always(self, msg, color=False):
        c_msg = self._color_message(msg) if color else msg
        self.gcode.respond_raw(c_msg)

    def log_error(self, msg):
        self.gcode.respond_raw("!! %s" % msg)

    def save_variable(self, variable, value, write=False):
        self.save_variables.allVariables[variable] = value
        if write:
            self.write_variables()

    def delete_variable(self, variable, write=False):
        _ = self.save_variables.allVariables.pop(variable, None)
        if write:
            self.write_variables()

    def write_variables(self):
        mmu_vars_revision = self.save_variables.allVariables.get(self.VARS_ACE_REVISION, 0) + 1
        self.gcode.run_script_from_command(
            "SAVE_VARIABLE VARIABLE=%s VALUE=%d" % (self.VARS_ACE_REVISION, mmu_vars_revision))


    def _get_next_request_id(self) -> int:
        """Get next sequential request ID with wraparound"""
        self._request_id += 1
        if self._request_id >= MAX_REQUEST_ID:
            self._request_id = 0
        return self._request_id

    def _validate_gate_index(self, index: int, param_name: str = "index") -> None:
        """Validate gate index is within valid range"""
        if index < 0 or index >= self.num_gates:
            raise AceException(f"Invalid {param_name}: {index} (valid range: 0-{self.num_gates-1})")

    def _validate_positive(self, value: int, param_name: str) -> None:
        """Validate value is positive"""
        if value <= 0:
            raise AceException(f"Invalid {param_name}: {value} (must be > 0)")

    def _validate_temperature(self, temp: int, max_temp: int) -> None:
        """Validate temperature is within safe range"""
        if temp <= 0 or temp > max_temp:
            raise AceException(f"Invalid temperature: {temp} (valid range: 1-{max_temp})")

    def _create_standard_callback(self, success_msg: Optional[str] = None, error_handler: Optional[Callable] = None):
        """Create a standard callback for ACE requests"""
        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                error_msg = response.get('msg', 'Unknown error')
                self.log_error(f"ACE Error: {error_msg}")
                if error_handler:
                    error_handler(response)
                return

            if success_msg:
                self.gcode.respond_info(success_msg)

            logging.debug(f"ACE request successful: {response.get('method', 'unknown')}")

        return callback

    def _serial_disconnect(self) -> None:
        """Safely disconnect from serial port and cleanup timers"""
        try:
            if self._serial is not None and self._serial.is_open:
                self._serial.close()
                logging.info(f"ACE: Closed connection to {self.serial_id}")
        except Exception as e:
            logging.error(f"ACE: Error closing serial port: {e}")
        finally:
            self._connected = False

        try:
            if hasattr(self, 'reader_timer'):
                self.reactor.unregister_timer(self.reader_timer)
            if hasattr(self, 'writer_timer'):
                self.reactor.unregister_timer(self.writer_timer)
        except Exception as e:
            logging.error(f"ACE: Error unregistering timers: {e}")

        # Reset state
        with self._lock:
            self._request_in_flight = False
            self._pending_request_id = None
        self.read_buffer = bytearray()

    def _connect(self, eventtime):
        """Attempt to connect to ACE device via serial port"""
        logging.info(f'ACE: Attempting connection to {self.serial_id}')

        def info_callback(self, response):
            """Handle device info response after connection"""
            if 'code' in response and response['code'] != 0:
                self.log_error(f"ACE Error: {response.get('msg', 'Unknown error')}")
                return

            result = response.get('result', {})
            model = result.get('model', 'Unknown')
            firmware = result.get('firmware', 'Unknown')

            self.log_always("{2}ACE: Connected to %s {0} \n Firmware Version: {3}%s{0}" %
                            (model, firmware), True)

            # Log firmware info for debugging chaining issues
            logging.info(f'ACE: Device Model: {model}, Firmware: {firmware}')
            logging.debug(f'ACE: Full device info: {json.dumps(result, indent=2)}')

            # Check if response contains any chain-related information
            if 'chain_mode' in result or 'num_devices' in result:
                logging.info('ACE: Chain information detected in device info')
            else:
                logging.debug('ACE: No chain information in device info')

        try:
            self._serial = serial.Serial(
                port=self.serial_id,
                baudrate=self.baud,
                exclusive=True,
                rtscts=True,
                timeout=0,
                write_timeout=0)

            if self._serial.is_open:
                # Reset state for new connection
                self._connected = True
                self._request_id = 0
                with self._lock:
                    self._request_in_flight = False
                    self._pending_request_id = None
                self.read_buffer = bytearray()

                logging.info(f'ACE: Successfully connected to {self.serial_id}')

                # Start communication timers
                self.writer_timer = self.reactor.register_timer(self._writer, eventtime + READY_WAIT_DELAY)
                self.reader_timer = self.reactor.register_timer(self._reader, eventtime + READY_WAIT_DELAY)

                # Request device info
                self.send_request(
                    request={"method": "get_info"},
                    callback=lambda self, response: info_callback(self, response))

                # Re-enable feed assist if it was previously enabled
                if self._feed_assist_index != -1:
                    logging.info(f'ACE: Re-enabling feed assist for gate {self._feed_assist_index}')
                    try:
                        self._enable_feed_assist(self._feed_assist_index)
                    except Exception as e:
                        logging.error(f'ACE: Failed to re-enable feed assist: {e}')

                # Stop connection retry timer
                if hasattr(self, 'connect_timer'):
                    self.reactor.unregister_timer(self.connect_timer)

                return self.reactor.NEVER

        except serial.serialutil.SerialException as e:
            self._serial = None
            logging.warning(f'ACE: Serial connection error to {self.serial_id}: {e}')
            self.log_error(f'Cannot connect to {self.serial_id} - retrying...')
        except Exception as e:
            self._serial = None
            logging.error(f'ACE: Unexpected connection error: {e}')
            self.log_error(f"ACE connection error: {e}")

        # Retry connection after delay
        return eventtime + CONNECT_RETRY_DELAY

    def _reconnect_with_backoff(self, eventtime):
        """Reconnect with exponential backoff after connection loss"""
        max_retries = 10
        base_delay = 1.0
        max_delay = 30.0

        if self._connection_retry_count >= max_retries:
            self.log_error(f"Failed to reconnect to ACE after {max_retries} attempts")
            self.log_error("Please check device connection and restart Klipper")
            return self.reactor.NEVER

        # Try to reconnect
        try:
            result = self._connect(eventtime)
            if result == self.reactor.NEVER:
                # Success - reset retry counter
                self._connection_retry_count = 0
                logging.info(f"ACE: Successfully reconnected to {self.serial_id}")
                self.log_always(f"{{2}}ACE: Reconnected to {self.serial_id}{{0}}", True)
                return self.reactor.NEVER
        except Exception as e:
            logging.warning(f"ACE: Reconnection attempt {self._connection_retry_count + 1} failed: {e}")

        # Calculate backoff delay
        self._connection_retry_count += 1
        delay = min(base_delay * (2 ** self._connection_retry_count), max_delay)

        logging.info(f"ACE: Retrying connection in {delay:.1f}s... (attempt {self._connection_retry_count}/{max_retries})")
        return eventtime + delay

    def _calc_crc(self, buffer: bytes) -> int:
        """Calculate CRC16 for ACE protocol"""
        _crc = CRC_INIT_VALUE
        for byte in buffer:
            data = byte
            data ^= _crc & 0xff
            data ^= (data & 0x0f) << 4
            _crc = ((data << 8) | (_crc >> 8)) ^ (data >> 4) ^ (data << 3)
        return _crc

    def _send_request(self, request: Dict[str, Any]) -> None:
        """Send a JSON-RPC request to ACE device"""
        if 'id' not in request:
            request['id'] = self._get_next_request_id()

        payload = json.dumps(request)
        payload = bytes(payload, 'utf-8')

        data = PROTOCOL_HEAD_BYTES
        data += struct.pack('@H', len(payload))
        data += payload
        data += struct.pack('@H', self._calc_crc(payload))
        data += bytes([PROTOCOL_TAIL_BYTE])
        self._serial.write(data)

    def _reader(self, eventtime):
        # Check for request timeout
        with self._lock:
            if self._request_in_flight and self.send_time and (self.reactor.monotonic() - self.send_time) > REQUEST_TIMEOUT:
                self._request_in_flight = False
                self._pending_request_id = None
                self.read_buffer = bytearray()
                self.log_warning(f"Request timeout after {REQUEST_TIMEOUT}s")

        try:
            with self._lock:
                should_read = self._request_in_flight

            if should_read and self._serial.in_waiting:
                raw_bytes = self._serial.read(size=self._serial.in_waiting)
            else:
                raw_bytes = bytearray()
        except serial.SerialException as e:
            self.log_error(f"ACE communication error: {e}")

            # Check if device still exists
            if not os.path.exists(self.serial_id):
                self.log_warning(f"ACE device {self.serial_id} disconnected")
                self.log_warning("Waiting for device to reconnect...")

                # Enter reconnection mode with exponential backoff
                self._serial_disconnect()
                self._connection_retry_count = 0
                self.connect_timer = self.reactor.register_timer(
                    self._reconnect_with_backoff,
                    self.reactor.NOW
                )
                return self.reactor.NEVER

            # Device exists but communication failed - try to recover
            self.log_warning("Communication failed, attempting to reconnect...")
            self._serial_disconnect()
            self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
            return self.reactor.NEVER
        except Exception as e:
            self.log_error(f"Unable to communicate with the ACE PRO: {e}")
            self.log_warning("Attempting to reconnect...")
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self._serial_disconnect()
            self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
            return self.reactor.NEVER

        if len(raw_bytes):
            text_buffer = self.read_buffer + raw_bytes
            i = text_buffer.find(b'\xfe')
            if i >= 0:
                buffer = text_buffer
                self.read_buffer = bytearray()
            else:
                self.read_buffer += raw_bytes
                return eventtime + READER_POLL_INTERVAL
        else:
            return eventtime + READER_POLL_INTERVAL

        if len(buffer) < PROTOCOL_MIN_PACKET_SIZE:
            return eventtime + READER_POLL_INTERVAL

        if buffer[0:2] != PROTOCOL_HEAD_BYTES:
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self.log_warning("Invalid protocol header from ACE PRO")
            logging.debug(f"Invalid buffer: {buffer.hex()}")
            return eventtime + READER_POLL_INTERVAL

        payload_len = struct.unpack('<H', buffer[2:4])[0]
        payload = buffer[4:4 + payload_len]

        crc_data = buffer[4 + payload_len:4 + payload_len + 2]
        crc = struct.pack('@H', self._calc_crc(payload))

        if len(buffer) < (4 + payload_len + 2 + 1):
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self.log_warning(f"Incomplete packet from ACE PRO: expected {4 + payload_len + 3}, got {len(buffer)}")
            return eventtime + READER_POLL_INTERVAL

        if crc_data != crc:
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self.log_error(f"CRC mismatch from ACE PRO: expected {crc.hex()}, got {crc_data.hex()}")
            return eventtime + READER_POLL_INTERVAL

        try:
            ret = json.loads(payload.decode('utf-8'))
            request_id = ret.get('id')

            with self._lock:
                if request_id in self._callback_map:
                    callback = self._callback_map.pop(request_id)
                    self._request_in_flight = False
                    self._pending_request_id = None
                    # Execute callback outside lock to prevent deadlock
                    callback(self=self, response=ret)
                else:
                    logging.warning(f"ACE: Received response for unknown request ID {request_id}")
        except (json.JSONDecodeError, KeyError) as e:
            self.log_error(f"Invalid JSON response from ACE PRO: {e}")
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None

        return eventtime + READER_POLL_INTERVAL

    def _writer(self, eventtime):
        try:
            def callback(self, response):
                if response is not None:
                    self._info = response.get('result', {})
                    # Dynamically detect number of gates from response
                    if 'slots' in self._info and len(self._info['slots']) > 0:
                        detected_gates = len(self._info['slots'])
                        if detected_gates != self.num_gates:
                            self.num_gates = detected_gates
                            self.gate_status = ['empty'] * self.num_gates
                            logging.info(f'ACE: Detected {self.num_gates} gates (chained devices)')
                            # Debug: Log the full response to help diagnose chaining issues
                            logging.debug(f'ACE: Full status response: {json.dumps(self._info, indent=2)}')
                    self.gate_status = [data['status'] for data in self._info.get('slots', [])]

            with self._lock:
                can_send = not self._request_in_flight

            if can_send:
                # Check for queued user requests first
                task = None
                try:
                    task = self._queue.get_nowait()
                except queue.Empty:
                    pass

                if task is not None:
                    request_id = self._get_next_request_id()
                    with self._lock:
                        self._callback_map[request_id] = task[1]
                        self._request_in_flight = True
                        self._pending_request_id = request_id
                    task[0]['id'] = request_id
                    self._send_request(task[0])
                    self.send_time = self.reactor.monotonic()
                else:
                    # Only poll status if no user requests pending
                    request_id = self._get_next_request_id()
                    with self._lock:
                        self._callback_map[request_id] = callback
                        self._request_in_flight = True
                        self._pending_request_id = request_id
                    self._send_request({"id": request_id, "method": "get_status"})
                    self.send_time = self.reactor.monotonic()

        except Exception as e:
            logging.error(f'ACE writer error: {e}\n{traceback.format_exc()}')
            with self._lock:
                self._request_in_flight = False
                self._pending_request_id = None
            self.log_error('Communication error - attempting reconnection')
            self._serial_disconnect()
            self.connect_timer = self.reactor.register_timer(self._connect, self.reactor.NOW)
            return self.reactor.NEVER

        return eventtime + WRITER_POLL_INTERVAL

    def send_request(self, request, callback):
        self._info['status'] = 'busy'
        self._queue.put([request, callback])



    def wait_ace_ready(self):
        while self._info['status'] != 'ready':
            currTs = self.reactor.monotonic()
            self.reactor.pause(currTs + .5)

    def is_ace_ready(self):
        return self._info['status'] == 'ready'

    def dwell(self, delay=1.):
        currTs = self.reactor.monotonic()
        self.reactor.pause(currTs + delay)

    def _extruder_move(self, length, speed):
        pos = self.toolhead.get_position()
        pos[3] += length
        self.toolhead.move(pos, speed)
        return pos[3]



    def extruder_sensor_handler(self, eventtime, is_filament_present, runout_helper):
        was_index = self.save_variables.allVariables.get('ace_current_index', -1)
        now = self.reactor.monotonic()
        print_stats = self.printer.lookup_object("print_stats", None)
        if print_stats is not None:
            is_printing = print_stats.get_status(now)["state"] == "printing"
        else:
            is_printing = self.printer.lookup_object("idle_timeout").get_status(now)["state"] == "Printing"

        if (not is_filament_present) and self._info['slots'][was_index]['status'] == 'empty' and is_printing:
            ace_material = self.save_variables.allVariables.get('ace_gate_type',['', '', '', ''])
            self.save_variable('ace_current_index', -1, True)
            pause_resume = self.printer.lookup_object('pause_resume')
            pause_resume.send_pause_command()

            if self.save_variables.allVariables.get('ace_endless_spool', False):
                self.log_always('Endless spool')
                spools = list(filter(lambda x: x['status'] != 'empty'
                                               and ace_material[x['index']] == ace_material[was_index],
                                     self._info['slots']))
                if len(spools) == 0:
                    self.log_warning("There are no suitable spools for an endless spool. Print pause")
                    return
                self.log_always('{2}Change to spool: %s{0}' % spools[0]["index"], True)
                self.gcode.run_script_from_command(f'T{spools[0]["index"]}')
                pause_resume.send_resume_command()
            else:
                self.log_warning('Filament runout! Endless spool disabled')

    def _create_mmu_sensor(self, config, pin, name, handler=None):
        # Instead of trying to load a full filament_switch_sensor object,
        # we'll create our own minimal implementation using just the endstop
        section = "filament_switch_sensor %s" % name

        # Create our custom runout helper that handles all the logic
        ro_helper = MmuRunoutHelper(self.printer, name, 0.1, '', '', '',
                                    False, handler, pin)

        # Create a minimal sensor object with just what we need
        class MinimalSensor:
            def __init__(self, helper, endstop_pin):
                self.runout_helper = helper
                self.get_status = helper.get_status
                self.name = helper.name
                self.pin = endstop_pin

        # Set up the endstop pin for monitoring
        ppins = self.printer.lookup_object('pins')
        pin_params = ppins.parse_pin(pin, True, True)
        share_name = "%s:%s" % (pin_params['chip_name'], pin_params['pin'])
        ppins.allow_multi_use_pin(share_name)
        mcu_endstop = ppins.setup_pin('endstop', pin)

        # Create the minimal sensor object
        fs = MinimalSensor(ro_helper, mcu_endstop)

        # Store the endstop for later use
        self.endstops[name] = mcu_endstop

        # Store the sensor in printer's objects so lookup_object can find it
        self.printer.objects[section] = fs

        # Register the endstop when klippy is ready (query_endstops may not exist yet)
        def register_endstop():
            try:
                query_endstops = self.printer.lookup_object('query_endstops')
                query_endstops.register_endstop(mcu_endstop, share_name)
            except:
                logging.info(f"ACE: query_endstops not available for {name}")

            # Set up polling for this sensor
            self._setup_sensor_polling(mcu_endstop, ro_helper)

        self.printer.register_event_handler("klippy:ready", register_endstop)

    def _setup_sensor_polling(self, endstop, helper):
        # Set up periodic polling of the sensor state
        def poll_sensor(eventtime):
            # Query the endstop state
            try:
                state = endstop.query_endstop(eventtime)
                helper.note_filament_present(eventtime, state)
            except:
                pass
            return eventtime + 0.1  # Poll every 100ms

        self.reactor.register_timer(poll_sensor, self.reactor.NOW)



    cmd_ACE_START_DRYING_help = 'Starts ACE Pro dryer'

    def cmd_ACE_START_DRYING(self, gcmd):
        temperature = gcmd.get_int('TEMP')
        duration = gcmd.get_int('DURATION', 240)

        if duration <= 0:
            raise gcmd.error('Wrong duration')
        if temperature <= 0 or temperature > self.max_dryer_temperature:
            raise gcmd.error('Wrong temperature')

        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])
                return

            self.gcode.respond_info('Started ACE drying')

        self.send_request(
            request={"method": "drying", "params": {"temp": temperature, "fan_speed": 7000, "duration": duration}},
            callback=callback)

    cmd_ACE_STOP_DRYING_help = 'Stops ACE Pro dryer'

    def cmd_ACE_STOP_DRYING(self, gcmd):
        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])
                return

            self.gcode.respond_info('Stopped ACE drying')

        self.send_request(request={"method": "drying_stop"}, callback=callback)

    def _enable_feed_assist(self, index: int) -> None:
        """Enable feed assist for a specific gate"""
        self._validate_gate_index(index)

        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])
            else:
                self._feed_assist_index = index
                logging.debug(f"Feed assist enabled for gate {index}")

        self.send_request(request={"method": "start_feed_assist", "params": {"index": index}}, callback=callback)
        self.dwell(delay=FEED_ASSIST_DELAY)

    cmd_ACE_ENABLE_FEED_ASSIST_help = 'Enables ACE feed assist'

    def cmd_ACE_ENABLE_FEED_ASSIST(self, gcmd):
        index = gcmd.get_int('INDEX')

        if index < 0 or index >= self.num_gates:
            raise gcmd.error(f'Wrong index (valid range: 0-{self.num_gates-1})')

        self._enable_feed_assist(index)

    def _disable_feed_assist(self, index: int) -> None:
        """Disable feed assist for a specific gate"""
        self._validate_gate_index(index)

        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])
                return

            self._feed_assist_index = -1
            logging.debug(f"Feed assist disabled for gate {index}")

        self.send_request(request={"method": "stop_feed_assist", "params": {"index": index}}, callback=callback)
        self.dwell(FEED_ASSIST_DISABLE_DELAY)

    cmd_ACE_DISABLE_FEED_ASSIST_help = 'Disables ACE feed assist'

    def cmd_ACE_DISABLE_FEED_ASSIST(self, gcmd):
        if self._feed_assist_index != -1:
            index = gcmd.get_int('INDEX', self._feed_assist_index)
        else:
            index = gcmd.get_int('INDEX')

        if index < 0 or index >= self.num_gates:
            raise gcmd.error(f'Wrong index (valid range: 0-{self.num_gates-1})')

        self._disable_feed_assist(index)

    def _feed(self, index: int, length: int, speed: int, how_wait: Optional[int] = None) -> None:
        """Feed filament from ACE to extruder"""
        self._validate_gate_index(index)
        self._validate_positive(length, "length")
        self._validate_positive(speed, "speed")

        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response.get('msg', 'Unknown error'))
                return

        self.send_request(
            request={"method": "feed_filament", "params": {"index": index, "length": length, "speed": speed}},
            callback=callback)
        wait_time = (how_wait if how_wait is not None else length) / speed + 0.1
        self.dwell(delay=wait_time)

    cmd_ACE_FEED_help = 'Feeds filament from ACE'

    def cmd_ACE_FEED(self, gcmd):
        index = gcmd.get_int('INDEX')
        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', self.feed_speed)

        if index < 0 or index >= self.num_gates:
            raise gcmd.error(f'Wrong index (valid range: 0-{self.num_gates-1})')
        if length <= 0:
            raise gcmd.error('Wrong length')
        if speed <= 0:
            raise gcmd.error('Wrong speed')

        self._feed(index, length, speed)

    def _retract(self, index: int, length: int, speed: int) -> None:
        """Retract filament back to ACE"""
        self._validate_gate_index(index)
        self._validate_positive(length, "length")
        self._validate_positive(speed, "speed")

        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response.get('msg', 'Unknown error'))
                return

        self.send_request(
            request={"method": "unwind_filament", "params": {"index": index, "length": length, "speed": speed}},
            callback=callback)
        self.dwell(delay=(length / speed) + 0.1)

    cmd_ACE_RETRACT_help = 'Retracts filament back to ACE'

    def cmd_ACE_RETRACT(self, gcmd):
        index = gcmd.get_int('INDEX')
        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', self.retract_speed)

        if index < 0 or index >= self.num_gates:
            raise gcmd.error(f'Wrong index (valid range: 0-{self.num_gates-1})')
        if length <= 0:
            raise gcmd.error('Wrong length')
        if speed <= 0:
            raise gcmd.error('Wrong speed')

        self._retract(index, length, speed)

    def _set_feeding_speed(self, index, speed):
        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])

        self.send_request(
            request={"method": "update_feeding_speed", "params": {"index": index, "speed": speed}},
            callback=callback)

    def _stop_feeding(self, index):
        def callback(self, response):
            if 'code' in response and response['code'] != 0:
                self.log_error("ACE Error: " + response['msg'])
                return

        self.send_request(
            request={"method": "stop_feed_filament", "params": {"index": index}},
            callback=callback)

    def _park_to_toolhead(self, tool):

        sensor_extruder = self.printer.lookup_object("filament_switch_sensor extruder_sensor", None)

        self.wait_ace_ready()

        self.save_variable('ace_filament_pos', "bowden", True)
        start_fast_feed = self.reactor.monotonic()
        self._feed(tool,
                   self.toolchange_feed_length + self.toolhead_homing_max,
                   self.feed_speed,
                   0
                   )

        while not bool(sensor_extruder.runout_helper.filament_present):
            if (start_fast_feed and
                    (self.reactor.monotonic() - start_fast_feed) >= (self.toolchange_feed_length//self.feed_speed)):
                self._set_feeding_speed(tool, self.toolhead_homing_speed)
                start_fast_feed = 0

            if self.is_ace_ready():
                raise AceException('ACE Error: Load failed: Failed to reach toolhead sensor')
            self.dwell(delay=0.01)

        self._stop_feeding(tool)

        self.wait_ace_ready()

        self._enable_feed_assist(tool)

        self.save_variable('ace_filament_pos', "bowden", True)

        if 'toolhead_sensor' in self.endstops:
            toolhead_sensor = self.printer.lookup_object("filament_switch_sensor toolhead_sensor", None)
            while not bool(toolhead_sensor.runout_helper.filament_present):
                self._extruder_move(1, self.extruder_move_speed)
                self.dwell(delay=0.01)

        self.save_variable('ace_filament_pos', "toolhead", True)

        self._extruder_move(self.toolhead_sensor_to_nozzle_length, self.extruder_move_speed)
        self.save_variable('ace_filament_pos', "nozzle", True)

        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_move.reset_last_position()
        self.gcode.run_script_from_command(self.poop_macros)

    cmd_ACE_CHANGE_TOOL_help = 'Changes tool'

    def cmd_ACE_CHANGE_TOOL(self, gcmd):
        tool = gcmd.get_int('TOOL')
        sensor_extruder = self.printer.lookup_object("filament_switch_sensor %s" % "extruder_sensor", None)

        if tool < -1 or tool >= self.num_gates:
            raise gcmd.error(f'Wrong tool (valid range: -1 or 0-{self.num_gates-1})')

        was = self.save_variables.allVariables.get('ace_current_index', -1)
        if was == tool:
            self.log_always('ACE: Not changing tool, current index already ' + str(tool))
            return

        if tool != -1:
            status = self._info['slots'][tool]['status']
            if status != 'ready':
                self.log_error("ACE Error: This spool is not ready")
                self.gcode.run_script_from_command('_ACE_ON_EMPTY_ERROR INDEX=' + str(tool))
                return
        self.gcode.run_script_from_command('_ACE_PRE_TOOLCHANGE FROM=' + str(was) + ' TO=' + str(tool))

        logging.info('ACE: Toolchange ' + str(was) + ' => ' + str(tool))
        self.log_always('ACE: Toolchange ' + str(was) + ' => ' + str(tool))

        if was != -1:
            self._disable_feed_assist(was)
            self.wait_ace_ready()
            if self.save_variables.allVariables.get('ace_filament_pos', "spliter") == "nozzle":
                self.gcode.run_script_from_command(self.cut_macros)
                self.save_variable('ace_filament_pos', "toolhead", True)

            if self.save_variables.allVariables.get('ace_filament_pos', "spliter") == "toolhead":
                while bool(sensor_extruder.runout_helper.filament_present):
                    self._extruder_move(-20, self.extruder_move_speed)
                    self._retract(was, 20, self.retract_speed)
                    self.wait_ace_ready()
                self.save_variable('ace_filament_pos', "bowden", True)

            self.wait_ace_ready()

            self._retract(was, self.toolchange_retract_length, self.retract_speed)
            self.wait_ace_ready()
            self.save_variable('ace_filament_pos', "spliter", True)

            if tool != -1:
                try:
                    self._park_to_toolhead(tool)
                except AceException as e:
                    self.log_error(str(e))
        else:
            try:
                self._park_to_toolhead(tool)
            except AceException as e:
                self.log_error(str(e))

        gcode_move = self.printer.lookup_object('gcode_move')
        gcode_move.reset_last_position()

        self.gcode.run_script_from_command('_ACE_POST_TOOLCHANGE FROM=' + str(was) + ' TO=' + str(tool))
        gcode_move.reset_last_position()
        self.save_variable('ace_current_index', tool, True)
        self.log_always("{2}Tool %s load{0}" % tool, True)

    cmd_ACE_GATE_MAP_help = 'Set ace gate info'

    def cmd_ACE_GATE_MAP(self, gcmd):
        gate = gcmd.get_int('GATE', None)

        if gate is not None:
            color = gcmd.get('COLOR', None)
            type = gcmd.get('TYPE', None)
            temp = gcmd.get_int('TEMP', None)
            if not color and not type and not temp:
                gcmd.respond_info('ACE: Bad params')
                return
            if color is not None:
                if 'ace_gate_color' not in self.save_variables.allVariables:
                    self.save_variables.allVariables['ace_gate_color'] = ['FFFFFF', 'FFFFFF', 'FFFFFF', 'FFFFFF']
                self.save_variables.allVariables['ace_gate_color'][gate] = color
            if type is not None:
                if 'ace_gate_type' not in self.save_variables.allVariables:
                    self.save_variables.allVariables['ace_gate_type'] = ['', '', '', '']
                self.save_variables.allVariables['ace_gate_type'][gate] = type
            if temp is not None:
                if 'ace_gate_temp' not in self.save_variables.allVariables:
                    self.save_variables.allVariables['ace_gate_temp'] = [0, 0, 0, 0]
                self.save_variables.allVariables['ace_gate_temp'][gate] = temp
            self.write_variables()
        else:
            gcmd.respond_info('ACE_MAP' + str(gate))

    cmd_ACE_ENDLESS_SPOOL_help = 'Enable/disable ace endless spool'

    def cmd_ACE_ENDLESS_SPOOL(self, gcmd):
        enable = gcmd.get_int('ENABLE', 1)
        self.save_variable('ace_endless_spool', bool(enable), True)

    cmd_ACE_DEBUG_help = 'ACE Debug'

    def cmd_ACE_DEBUG(self, gcmd):
        method = gcmd.get('METHOD')
        params = gcmd.get('PARAMS', '{}')

        try:
            def callback(self, response):
                self.gcode.respond_info(str(response))

            self.send_request(request={"method": method, "params": json.loads(params)}, callback=callback)
        except Exception as e:
            self.gcode.respond_info('Error: ' + str(e))

    cmd_ACE_GET_STATUS_help = 'Get detailed ACE status including slot information'

    def cmd_ACE_GET_STATUS(self, gcmd):
        """Query and display full ACE status to help diagnose chaining issues"""
        def callback(self, response):
            if response is not None and 'result' in response:
                result = response['result']

                # Display summary
                self.gcode.respond_info('=== ACE Status ===')
                self.gcode.respond_info(f"Status: {result.get('status', 'unknown')}")
                self.gcode.respond_info(f"Temperature: {result.get('temp', 0)}°C")

                # Display slot information
                if 'slots' in result:
                    slots = result['slots']
                    self.gcode.respond_info(f"\n=== Slots ({len(slots)} detected) ===")
                    for slot in slots:
                        idx = slot.get('index', '?')
                        status = slot.get('status', 'unknown')
                        sku = slot.get('sku', 'N/A')
                        filament_type = slot.get('type', 'N/A')
                        color = slot.get('color', [0, 0, 0])
                        self.gcode.respond_info(
                            f"Slot {idx}: {status} | Type: {filament_type} | "
                            f"SKU: {sku} | Color: RGB{color}"
                        )
                else:
                    self.gcode.respond_info("No slot information in response")

                # Display dryer status if available
                if 'dryer_status' in result:
                    dryer = result['dryer_status']
                    self.gcode.respond_info(f"\n=== Dryer ===")
                    self.gcode.respond_info(
                        f"Status: {dryer.get('status', 'unknown')} | "
                        f"Target: {dryer.get('target_temp', 0)}°C | "
                        f"Remaining: {dryer.get('remain_time', 0)}min"
                    )

                # Display full JSON for debugging
                self.gcode.respond_info('\n=== Full Response (for debugging) ===')
                self.gcode.respond_info(json.dumps(result, indent=2))
            else:
                self.gcode.respond_info('No response or invalid response from ACE')

        self.send_request(request={"method": "get_status"}, callback=callback)

    def get_status(self, eventtime=None):
        # Ensure gate arrays match the detected number of gates
        default_colors = ['FFFFFF'] * self.num_gates
        default_types = [''] * self.num_gates
        default_temps = [230] * self.num_gates
        default_spool_ids = list(range(1, self.num_gates + 1))

        # Get saved variables and expand if needed
        gate_colors = list(self.save_variables.allVariables.get('ace_gate_color', default_colors))
        gate_types = list(self.save_variables.allVariables.get('ace_gate_type', default_types))
        gate_temps = list(self.save_variables.allVariables.get('ace_gate_temp', default_temps))

        # Extend arrays if more gates detected than previously saved
        while len(gate_colors) < self.num_gates:
            gate_colors.append('FFFFFF')
        while len(gate_types) < self.num_gates:
            gate_types.append('')
        while len(gate_temps) < self.num_gates:
            gate_temps.append(230)

        # Update saved variables if they were expanded
        if len(gate_colors) != len(self.save_variables.allVariables.get('ace_gate_color', [])):
            self.save_variable('ace_gate_color', gate_colors, True)
        if len(gate_types) != len(self.save_variables.allVariables.get('ace_gate_type', [])):
            self.save_variable('ace_gate_type', gate_types, True)
        if len(gate_temps) != len(self.save_variables.allVariables.get('ace_gate_temp', [])):
            self.save_variable('ace_gate_temp', gate_temps, True)

        return {
            'status': self._info['status'],
            'temp': self._info['temp'],
            'dryer_status': self._info['dryer_status'],
            'gate_color': gate_colors[:self.num_gates],
            'gate_material': gate_types[:self.num_gates],
            'gate_temp': gate_temps[:self.num_gates],
            'active_gate': self.gate_status,
            'spool_id': default_spool_ids,
            'selected_gate': int(self.save_variables.allVariables.get('ace_current_index', -1)),
            'endless_spool': bool(self.save_variables.allVariables.get('ace_endless_spool', False)),
            'num_gates': self.num_gates,
        }


class AceManager:
    """Manages multiple ACE Pro devices as a unified multi-gate system"""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.name = config.get_name()
        self.config = config

        # ACE device configuration
        self.ace_devices = []
        self.total_gates = 0
        self.use_direct_serial = False

        # Check which configuration method is used
        serial_ports_str = config.get('serial_ports', None)
        ace_devices_str = config.get('ace_devices', None)
        auto_detect = config.getboolean('auto_detect', False)

        # Pre-read all possible config parameters to make them "valid" in Klipper's eyes
        # This prevents "Option X is not valid" errors during config validation
        # We don't use these values here, but reading them registers them as valid options
        config.getint('baud', 115200)
        config.get('extruder_sensor_pin', None)
        config.get('toolhead_sensor_pin', None)
        config.getint('extruder_move_speed', 10)
        config.getint('toolhead_homing_speed', 20)
        config.getint('feed_speed', 80)
        config.getint('retract_speed', 80)
        config.getint('toolchange_retract_length', 170)
        config.getint('toolchange_feed_length', 800)
        config.getint('toolhead_sensor_to_nozzle', 40)
        config.get('poop_macros', '_POOP')
        config.get('cut_macros', '_CUT_TIP')
        config.getint('max_dryer_temperature', 70)

        if serial_ports_str:
            # Method 1: Direct serial ports (recommended)
            self.use_direct_serial = True
            self._setup_from_serial_ports(config, serial_ports_str)
        elif auto_detect:
            # Method 2: Auto-detect ACE devices
            self.use_direct_serial = True
            self._setup_auto_detect(config)
        elif ace_devices_str:
            # Method 3: Named ACE devices (backward compatible)
            self._setup_from_ace_devices(ace_devices_str)
        else:
            config.error("ace_manager requires one of: serial_ports, ace_devices, or auto_detect=true")

        # Calculate gate offsets
        offset = 0
        for device in self.ace_devices:
            device['gate_offset'] = offset
            offset += 4  # Each ACE has 4 gates

        self.total_gates = offset

        # Register event handlers
        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:connect', self._handle_connect)

        # Register unified commands (for all configuration methods)
        self.gcode.register_command(
            'ACE_CHANGE_TOOL', self.cmd_ACE_CHANGE_TOOL,
            desc=self.cmd_ACE_CHANGE_TOOL_help)
        self.gcode.register_command(
            'ACE_GET_STATUS', self.cmd_ACE_GET_STATUS,
            desc=self.cmd_ACE_GET_STATUS_help)
        self.gcode.register_command(
            'ACE_FEED', self.cmd_ACE_FEED,
            desc=self.cmd_ACE_FEED_help)
        self.gcode.register_command(
            'ACE_RETRACT', self.cmd_ACE_RETRACT,
            desc=self.cmd_ACE_RETRACT_help)
        self.gcode.register_command(
            'ACE_GATE_MAP', self.cmd_ACE_GATE_MAP,
            desc=self.cmd_ACE_GATE_MAP_help)
        self.gcode.register_command(
            'ACE_SCAN_DEVICES', self.cmd_ACE_SCAN_DEVICES,
            desc=self.cmd_ACE_SCAN_DEVICES_help)
        self.gcode.register_command(
            'ACE_LIST_DEVICES', self.cmd_ACE_LIST_DEVICES,
            desc=self.cmd_ACE_LIST_DEVICES_help)
        self.gcode.register_command(
            'ACE_SHOW_USB_INFO', self.cmd_ACE_SHOW_USB_INFO,
            desc=self.cmd_ACE_SHOW_USB_INFO_help)
        self.gcode.register_command(
            'ACE_REORDER_DEVICES', self.cmd_ACE_REORDER_DEVICES,
            desc=self.cmd_ACE_REORDER_DEVICES_help)
        # Dryer commands
        self.gcode.register_command(
            'ACE_START_DRYING', self.cmd_ACE_START_DRYING,
            desc=self.cmd_ACE_START_DRYING_help)
        self.gcode.register_command(
            'ACE_STOP_DRYING', self.cmd_ACE_STOP_DRYING,
            desc=self.cmd_ACE_STOP_DRYING_help)
        self.gcode.register_command(
            'ACE_GET_DRYER_STATUS', self.cmd_ACE_GET_DRYER_STATUS,
            desc=self.cmd_ACE_GET_DRYER_STATUS_help)

    def _setup_from_serial_ports(self, config, serial_ports_str):
        """Setup ACE devices from comma-separated serial port list"""
        import re

        # Parse comma-separated serial ports
        serial_ports = [p.strip() for p in serial_ports_str.split(',')]

        logging.info(f"ACE Manager: Setting up {len(serial_ports)} ACE devices from serial_ports")

        # Read parameters from fileconfig directly to bypass validation
        # This allows us to read parameters without Klipper complaining they're not "valid"
        def get_param(key, default=None):
            section = config.get_name()
            if config.fileconfig.has_option(section, key):
                return config.fileconfig.get(section, key)
            return default

        def get_param_int(key, default=None):
            val = get_param(key, default)
            return int(val) if val is not None else default

        # Create BunnyAce instances directly
        for i, port in enumerate(serial_ports):
            # Create a pseudo-config for this ACE instance
            ace_name = f"ace{i+1}"

            # Create config dict with all shared parameters
            # Get required extruder_sensor_pin (no default - must be present)
            extruder_pin = get_param('extruder_sensor_pin')
            if not extruder_pin:
                config.error("ace_manager requires 'extruder_sensor_pin' parameter")

            ace_config = {
                'serial': port,
                'baud': get_param_int('baud', 115200),
                'extruder_sensor_pin': extruder_pin,
                'toolhead_sensor_pin': get_param('toolhead_sensor_pin', None),
                'extruder_move_speed': get_param_int('extruder_move_speed', 10),
                'toolhead_homing_speed': get_param_int('toolhead_homing_speed', 20),
                'feed_speed': get_param_int('feed_speed', 80),
                'retract_speed': get_param_int('retract_speed', 80),
                'toolchange_retract_length': get_param_int('toolchange_retract_length', 170),
                'toolchange_feed_length': get_param_int('toolchange_feed_length', 800),
                'toolhead_sensor_to_nozzle': get_param_int('toolhead_sensor_to_nozzle', 40),
                'poop_macros': get_param('poop_macros', '_POOP'),
                'cut_macros': get_param('cut_macros', '_CUT_TIP'),
                'max_dryer_temperature': get_param_int('max_dryer_temperature', 70),
                'gate_offset': i * 4  # Calculate offset based on index
            }

            # Create a ConfigWrapper-like object
            class AceConfigWrapper:
                def __init__(self, printer, name, ace_config, parent_config):
                    self._printer = printer
                    self._name = name
                    self._config = ace_config
                    self.fileconfig = parent_config.fileconfig  # Pass through parent's fileconfig

                def get_printer(self):
                    return self._printer

                def get_name(self):
                    return self._name

                def get(self, key, default=None):
                    # Check if key exists in config
                    if key not in self._config:
                        if default is None:
                            # Key doesn't exist and no default - let Klipper handle the error
                            raise self.error(f"Option '{key}' in section '{self._name}' must be specified")
                        return default

                    val = self._config[key]
                    # If the stored value is None, return the default
                    if val is None:
                        return default
                    return val

                def getint(self, key, default=None, minval=None, maxval=None):
                    val = self.get(key, default)
                    if val is None:
                        if default is None:
                            raise self.error(f"Option '{key}' in section '{self._name}' must be specified")
                        return default
                    result = int(val)
                    if minval is not None and result < minval:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be >= {minval}")
                    if maxval is not None and result > maxval:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be <= {maxval}")
                    return result

                def getfloat(self, key, default=None, minval=None, maxval=None, above=None, below=None):
                    val = self.get(key, default)
                    if val is None:
                        if default is None:
                            raise self.error(f"Option '{key}' in section '{self._name}' must be specified")
                        return default
                    result = float(val)
                    if minval is not None and result < minval:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be >= {minval}")
                    if maxval is not None and result > maxval:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be <= {maxval}")
                    if above is not None and result <= above:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be > {above}")
                    if below is not None and result >= below:
                        raise self.error(f"Option '{key}' in section '{self._name}' must be < {below}")
                    return result

                def getboolean(self, key, default=None):
                    val = self.get(key, default)
                    if val is None:
                        return default
                    if isinstance(val, bool):
                        return val
                    # Handle string boolean values
                    if isinstance(val, str):
                        val = val.lower()
                        if val in ('true', '1', 'yes'):
                            return True
                        elif val in ('false', '0', 'no'):
                            return False
                    return bool(val)

                def getchoice(self, key, choices, default=None):
                    val = self.get(key, default)
                    if val is None:
                        if default is None:
                            raise self.error(f"Option '{key}' in section '{self._name}' must be specified")
                        return default
                    if val not in choices:
                        raise self.error(f"Option '{key}' in section '{self._name}' is not a valid choice")
                    return val

                def getlist(self, key, default=None):
                    val = self.get(key, default)
                    if val is None:
                        if default is None:
                            return []
                        return default
                    if isinstance(val, list):
                        return val
                    # Parse comma-separated string
                    return [item.strip() for item in str(val).split(',') if item.strip()]

                def getsection(self, section):
                    # When loading dynamically created sections (like filament sensors),
                    # we need to return a config that reads from fileconfig
                    # Create a wrapper that reads from fileconfig for the requested section
                    class FileconfigSectionWrapper:
                        def __init__(self, parent_wrapper, section_name):
                            self._parent = parent_wrapper
                            self._section = section_name
                            self.fileconfig = parent_wrapper.fileconfig

                        def get_printer(self):
                            return self._parent.get_printer()

                        def get_name(self):
                            return self._section

                        def get(self, key, default=None):
                            if self.fileconfig.has_option(self._section, key):
                                return self.fileconfig.get(self._section, key)
                            if default is None:
                                raise Exception(f"Option '{key}' in section '{self._section}' must be specified")
                            return default

                        def getint(self, key, default=None, minval=None, maxval=None):
                            val = self.get(key, default)
                            if val is None:
                                return default
                            return int(val)

                        def getfloat(self, key, default=None, minval=None, maxval=None, above=None, below=None):
                            val = self.get(key, default)
                            if val is None:
                                return default
                            return float(val)

                        def getboolean(self, key, default=None):
                            val = self.get(key, default)
                            if val is None:
                                return default
                            if isinstance(val, str):
                                val = val.lower()
                                return val in ('true', '1', 'yes')
                            return bool(val)

                        def getchoice(self, key, choices, default=None):
                            val = self.get(key, default)
                            if val and val not in choices:
                                raise Exception(f"Option '{key}' in section '{self._section}' is not valid")
                            return val

                        def getlist(self, key, default=None):
                            val = self.get(key, default)
                            if val is None:
                                if default is None:
                                    return []
                                return default
                            if isinstance(val, list):
                                return val
                            return [item.strip() for item in str(val).split(',') if item.strip()]

                        def getsection(self, section):
                            return self

                        def error(self, msg):
                            raise Exception(msg)

                    return FileconfigSectionWrapper(self, section)

                def error(self, msg):
                    raise Exception(msg)

            # Create ACE instance
            ace_wrapper = AceConfigWrapper(self.printer, f"ace {ace_name}", ace_config, config)
            ace_instance = BunnyAce(ace_wrapper)

            # Get device_id from device_ids mapping, or generate fallback
            device_id = self.device_ids.get(port, f"port_{i}")  # Fallback for non-auto-detect

            # Store device info
            self.ace_devices.append({
                'name': ace_name,
                'port': port,
                'instance': ace_instance,
                'gate_offset': i * 4,
                'device_id': device_id
            })

            logging.info(f"ACE Manager: Created {ace_name} (ID: {device_id}) on {port} with gate offset {i * 4}")

    def _setup_auto_detect(self, config):
        """Auto-detect ACE devices and create instances using USB enumeration"""
        logging.info("ACE Manager: Auto-detecting ACE devices via USB enumeration...")

        # Use shared enumeration logic
        enum_plan = self._reenumerate_devices()

        discovered_devices = enum_plan['discovered_devices']

        if not discovered_devices:
            logging.warning("ACE Manager: No ACE devices found via USB enumeration")
            logging.warning("ACE Manager: Please check USB connections and verify ACE devices are powered on")
            # Don't fail - devices might be connected later
            return

        logging.info(f"ACE Manager: Found {len(discovered_devices)} ACE device(s)")

        # Build serial ports string and store device IDs
        serial_ports_str = ', '.join([dev['port'] for dev in discovered_devices])

        logging.info(f"ACE Manager: Configuring {len(discovered_devices)} ACE device(s) with {len(discovered_devices) * 4} total gates")
        logging.info(f"ACE Manager: Port order: {serial_ports_str}")

        # Store device IDs for reconnection logic (will be used in _handle_ready)
        self.device_ids = {dev['port']: dev['device_id'] for dev in discovered_devices}
        self._verified_devices = discovered_devices  # Save for device mapper initialization

        # Use existing serial port setup with discovered ports
        self._setup_from_serial_ports(config, serial_ports_str)

    def _setup_from_ace_devices(self, ace_devices_str):
        """Setup from named ACE device configs (backward compatible)"""
        device_names = [name.strip() for name in ace_devices_str.split(',')]

        logging.info(f"ACE Manager: Setting up {len(device_names)} named ACE devices")

        for i, name in enumerate(device_names):
            self.ace_devices.append({
                'name': name,
                'port': 'managed',  # Will be set by individual config
                'instance': None,  # Will be linked in _handle_ready
                'gate_offset': 0,  # Will be calculated
                'device_id': f"named_{name}"  # Fallback ID for named devices
            })

    def _handle_ready(self):
        """Link to ACE instances after all configs are loaded"""
        # Only link instances if using backward-compatible named device mode
        if not self.use_direct_serial:
            for device in self.ace_devices:
                ace_name = f"ace {device['name']}"
                try:
                    device['instance'] = self.printer.lookup_object(ace_name)
                    logging.info(f"ACE Manager: Linked to {ace_name} at gate offset {device['gate_offset']}")
                except:
                    raise self.printer.config_error(
                        f"ACE Manager: Cannot find ACE device '{ace_name}'. "
                        f"Make sure [ace {device['name']}] is configured.")

        # Initialize device mapper for auto-detect mode
        if hasattr(self, '_verified_devices') and self._verified_devices:
            # Get config directory from first ACE device's save_variables
            if self.ace_devices and self.ace_devices[0]['instance']:
                first_ace = self.ace_devices[0]['instance']
                if hasattr(first_ace, 'save_variables') and first_ace.save_variables:
                    # Get the variables file path
                    try:
                        # Look up the save_variables object to get its filename
                        save_vars = self.printer.lookup_object('save_variables')
                        if hasattr(save_vars, 'filename'):
                            config_dir = os.path.dirname(save_vars.filename)
                        else:
                            config_dir = os.path.expanduser('~/printer_data/config')
                    except:
                        config_dir = os.path.expanduser('~/printer_data/config')

                    map_file = os.path.join(config_dir, 'ace_device_map.cfg')
                    self.device_mapper = AceDeviceMapper(map_file)

                    # Track configuration changes for user notification
                    config_changes = []

                    # Update device map with verified devices and track changes
                    for i, dev in enumerate(self._verified_devices):
                        device_id = dev['device_id']
                        port = dev['port']
                        usb_location = dev.get('usb_location', '')
                        current_gate_offset = i * 4  # Gates assigned based on current device order

                        # Check if this is a known device with previous configuration
                        prev_info = self.device_mapper.get_device_info(device_id)
                        if prev_info and 'last_gate_offset' in prev_info:
                            prev_gate_offset = prev_info['last_gate_offset']
                            if prev_gate_offset != current_gate_offset:
                                config_changes.append({
                                    'device_id': device_id,
                                    'usb_location': usb_location,
                                    'prev_gate_offset': prev_gate_offset,
                                    'new_gate_offset': current_gate_offset
                                })

                        # Update device mapping with current configuration
                        self.device_mapper.update_device(device_id, port, usb_location, current_gate_offset)
                        logging.info(f"ACE Manager: Mapped device {device_id} to {port} at gates {current_gate_offset}-{current_gate_offset+3}")

                    # Log configuration changes
                    if config_changes:
                        logging.info("=" * 60)
                        logging.info("ACE Manager: Device configuration has changed since last boot")
                        for change in config_changes:
                            prev_gates = f"{change['prev_gate_offset']}-{change['prev_gate_offset']+3}"
                            new_gates = f"{change['new_gate_offset']}-{change['new_gate_offset']+3}"
                            logging.info(f"  {change['device_id']}: Gates {prev_gates} → {new_gates}")
                        logging.info("Device properties (colors, materials, temps) will follow the device")
                        logging.info("=" * 60)

                    # Migrate device properties to current ACE instances
                    # Properties persist with the device, not the gate offset
                    self._migrate_device_properties_to_ace_instances()

                    # Save device map
                    self.device_mapper.save()
                    logging.info(f"ACE Manager: Device map saved to {map_file}")

        logging.info(f"ACE Manager: Managing {len(self.ace_devices)} ACE devices with {self.total_gates} total gates")

    def _migrate_device_properties_to_ace_instances(self):
        """
        Migrate device properties from device mapper to ACE instances.
        Device properties (colors, materials, temps) persist with the device,
        not with the gate offset, so they follow the device when it changes ports.
        """
        if not hasattr(self, 'device_mapper'):
            return

        for ace_device in self.ace_devices:
            device_id = ace_device.get('device_id')
            if not device_id:
                continue

            ace_instance = ace_device.get('instance')
            if not ace_instance:
                continue

            # Get stored properties for this device
            device_props = self.device_mapper.get_device_properties(device_id)

            if not device_props:
                # No stored properties, initialize default properties from current ACE state
                # and save them for future reference
                if hasattr(ace_instance, 'save_variables'):
                    current_colors = ace_instance.save_variables.allVariables.get('ace_gate_color', [])
                    current_materials = ace_instance.save_variables.allVariables.get('ace_gate_type', [])
                    current_temps = ace_instance.save_variables.allVariables.get('ace_gate_temp', [])

                    if current_colors or current_materials or current_temps:
                        device_props = {
                            'gate_colors': current_colors,
                            'gate_materials': current_materials,
                            'gate_temps': current_temps
                        }
                        self.device_mapper.update_device_properties(device_id, device_props)
                        logging.info(f"ACE Manager: Initialized properties for device {device_id}")
                continue

            # Apply stored properties to ACE instance
            # Note: Properties are stored per-device (4 gates), not per global gate offset
            if hasattr(ace_instance, 'save_variables'):
                if 'gate_colors' in device_props and device_props['gate_colors']:
                    ace_instance.save_variables.allVariables['ace_gate_color'] = device_props['gate_colors']
                    logging.info(f"ACE Manager: Restored gate colors for device {device_id}")

                if 'gate_materials' in device_props and device_props['gate_materials']:
                    ace_instance.save_variables.allVariables['ace_gate_type'] = device_props['gate_materials']
                    logging.info(f"ACE Manager: Restored gate materials for device {device_id}")

                if 'gate_temps' in device_props and device_props['gate_temps']:
                    ace_instance.save_variables.allVariables['ace_gate_temp'] = device_props['gate_temps']
                    logging.info(f"ACE Manager: Restored gate temperatures for device {device_id}")

                # Also update the gate colors/materials on the ACE device itself
                # This will sync the properties to the physical device
                if hasattr(ace_instance, 'gate_color'):
                    ace_instance.gate_color = device_props.get('gate_colors', ace_instance.gate_color)
                if hasattr(ace_instance, 'gate_material'):
                    ace_instance.gate_material = device_props.get('gate_materials', ace_instance.gate_material)
                if hasattr(ace_instance, 'gate_temp'):
                    ace_instance.gate_temp = device_props.get('gate_temps', ace_instance.gate_temp)

    def _handle_connect(self):
        """Handle Klipper connection - attempt to reconnect to ACE devices if they moved ports"""
        if not hasattr(self, 'device_mapper') or not hasattr(self, 'device_ids'):
            # Not using auto-detect, skip reconnection logic
            return

        logging.info("ACE Manager: Klipper connected, checking ACE device ports...")

        # Re-scan USB to find current ports for known device IDs
        discovered = AceDeviceDiscovery.find_ace_devices()

        for device in self.ace_devices:
            # Get the device ID for this ACE instance
            device_id = self.device_ids.get(device.get('port'))
            if not device_id:
                continue

            # Try to find this device in current USB enumeration
            current_port = None
            for dev_info in discovered:
                port = dev_info['port']
                ace_info = AceDeviceDiscovery.probe_ace_device(port)
                if ace_info and ace_info['device_id'] == device_id:
                    current_port = port
                    break

            if current_port:
                # Check if port changed
                if current_port != device['port']:
                    logging.info(f"ACE Manager: Device {device_id} moved from {device['port']} to {current_port}")
                    old_port = device['port']
                    device['port'] = current_port
                    device['instance'].serial_id = current_port

                    # Update device mapper
                    self.device_mapper.update_device(device_id, current_port)
                    self.device_mapper.save()

                    # Update device_ids mapping
                    if old_port in self.device_ids:
                        del self.device_ids[old_port]
                    self.device_ids[current_port] = device_id

                    # Trigger reconnection in the BunnyAce instance
                    logging.info(f"ACE Manager: Triggering reconnection for {device_id} on {current_port}")
                else:
                    logging.info(f"ACE Manager: Device {device_id} still on {current_port}")
            else:
                logging.warning(f"ACE Manager: Device {device_id} not found, will retry on next connection")

    def _route_to_ace(self, global_gate):
        """Route a global gate number to the correct ACE instance and local gate"""
        if global_gate < 0 or global_gate >= self.total_gates:
            raise self.gcode.error(f"Invalid gate {global_gate} (valid: 0-{self.total_gates-1})")

        for device in self.ace_devices:
            offset = device['gate_offset']
            # Check if gate is in this device's range [offset, offset+4)
            if global_gate >= offset and global_gate < offset + 4:
                local_gate = global_gate - offset
                return device['instance'], local_gate

        raise self.gcode.error(f"Cannot route gate {global_gate}")

    cmd_ACE_CHANGE_TOOL_help = 'Changes tool (unified across all ACE devices)'

    def cmd_ACE_CHANGE_TOOL(self, gcmd):
        """Unified tool change that routes to correct ACE"""
        tool = gcmd.get_int('TOOL')

        if tool == -1:
            # Unload - determine which ACE has the loaded filament
            first_ace = self.ace_devices[0]['instance'] if self.ace_devices else None
            if first_ace:
                selected_gate = int(first_ace.save_variables.allVariables.get('ace_current_index', -1))

                if selected_gate >= 0:
                    # Route to the ACE that owns this gate
                    try:
                        ace_instance, local_tool = self._route_to_ace(selected_gate)

                        # Create gcmd with local unload (-1) but route to correct device
                        import types
                        local_gcmd = types.SimpleNamespace()
                        local_gcmd.get_int = lambda key, default=None: -1 if key == 'TOOL' else default
                        local_gcmd.error = gcmd.error

                        logging.info(f"ACE Manager: Routing unload command to device at gate offset {ace_instance.gate_offset}")
                        ace_instance.cmd_ACE_CHANGE_TOOL(local_gcmd)
                    except Exception as e:
                        self.gcode.respond_info(f"Error routing unload command: {e}")
                        logging.error(f"ACE Manager: Error routing unload: {e}")
                else:
                    # No tool loaded, nothing to unload
                    self.gcode.respond_info("No tool currently loaded")
                    logging.info("ACE Manager: Unload requested but no tool is loaded")
            return

        # Normal tool change - route to correct ACE
        ace_instance, local_tool = self._route_to_ace(tool)

        # Create new gcmd with local tool number
        import types
        local_gcmd = types.SimpleNamespace()
        local_gcmd.get_int = lambda key, default=None: local_tool if key == 'TOOL' else default
        local_gcmd.error = gcmd.error

        logging.info(f"ACE Manager: Routing tool change T{tool} to device at gate offset {ace_instance.gate_offset} (local T{local_tool})")
        ace_instance.cmd_ACE_CHANGE_TOOL(local_gcmd)

    def get_status(self, eventtime=None):
        """
        Get unified status from all ACE devices for Moonraker API.
        This method is required for the object to appear in /printer/objects/list
        """
        # Initialize aggregated arrays
        all_gate_colors = []
        all_gate_materials = []
        all_gate_temps = []
        all_active_gates = []
        all_spool_ids = []
        all_dryers = []  # NEW: Per-device dryer status

        # Aggregate temperatures and status from first device
        first_ace = self.ace_devices[0]['instance'] if self.ace_devices else None
        overall_temp = 0
        overall_status = 'ready'

        # Aggregate data from all ACE devices
        for device in self.ace_devices:
            ace = device['instance']
            offset = device['gate_offset']

            # Get status from this ACE
            status = ace.get_status()

            # Append this ACE's gate data to aggregated arrays
            all_gate_colors.extend(status.get('gate_color', []))
            all_gate_materials.extend(status.get('gate_material', []))
            all_gate_temps.extend(status.get('gate_temp', []))
            all_active_gates.extend(status.get('active_gate', []))

            # Generate spool IDs with global numbering
            num_gates = status.get('num_gates', 4)
            all_spool_ids.extend(range(offset + 1, offset + num_gates + 1))

            # Build dryer status for this device
            dryer_status = status.get('dryer_status', {
                'status': 'stop',
                'target_temp': 0,
                'duration': 0,
                'remain_time': 0
            })

            all_dryers.append({
                'device_id': device.get('device_id', f"dev_{offset}"),
                'device_name': device.get('name', f"ACE Unit {offset//4 + 1}"),
                'gate_offset': offset,
                'status': dryer_status.get('status', 'stop'),
                'temp': status.get('temp', 0),
                'target_temp': dryer_status.get('target_temp', 0),
                'duration': dryer_status.get('duration', 0),
                'remain_time': dryer_status.get('remain_time', 0)
            })

            # Use first ACE's temp and status
            if device == self.ace_devices[0]:
                overall_temp = status.get('temp', 0)
                overall_status = status.get('status', 'ready')

        # Get selected gate from first ACE's save variables
        selected_gate = -1
        if first_ace:
            selected_gate = int(first_ace.save_variables.allVariables.get('ace_current_index', -1))

        # Get endless spool setting from first ACE
        endless_spool = False
        if first_ace:
            endless_spool = bool(first_ace.save_variables.allVariables.get('ace_endless_spool', False))

        # Build device summary for web UI
        devices_summary = []
        for dev in self.ace_devices:
            ace = dev['instance']
            devices_summary.append({
                'device_id': dev.get('device_id', f"unknown_{dev['port']}"),
                'name': dev.get('name', f"ACE Unit {dev['gate_offset']//4 + 1}"),
                'connection_status': 'connected' if ace._connected else 'disconnected',
                'gate_offset': dev['gate_offset'],
                'health': self._get_device_health(ace)
            })

        # Build per-device gate data with device-specific variables
        # This allows UI to know which gates belong to which device
        devices_detail = []
        for dev in self.ace_devices:
            ace = dev['instance']
            status = ace.get_status()
            device_id = dev.get('device_id', f"dev_{dev['gate_offset']}")

            # Get gate configuration from device properties (stored in device mapper)
            # This ensures properties persist with the device across reboots/port changes
            if hasattr(self, 'device_mapper') and self.device_mapper:
                device_props = self.device_mapper.get_device_properties(device_id)
                gate_color = device_props.get('gate_colors', status.get('gate_color', ['FFFFFF'] * 4))
                gate_material = device_props.get('gate_materials', status.get('gate_material', [''] * 4))
                gate_temp = device_props.get('gate_temps', status.get('gate_temp', [230] * 4))
            else:
                # Fallback to ACE instance's own status
                gate_color = status.get('gate_color', ['FFFFFF'] * 4)
                gate_material = status.get('gate_material', [''] * 4)
                gate_temp = status.get('gate_temp', [230] * 4)

            # Get dryer status for this device
            dryer_status = status.get('dryer_status', {})

            devices_detail.append({
                'device_id': device_id,
                'gate_offset': dev['gate_offset'],
                'gate_color': gate_color,
                'gate_material': gate_material,
                'gate_temp': gate_temp,
                'active_gate': status.get('active_gate', []),
                'spool_id': list(range(dev['gate_offset'] + 1, dev['gate_offset'] + 5)),
                # NEW: Per-device dryer info
                'dryer_status': dryer_status,
                'dryer_temp': status.get('temp', 0)
            })

        return {
            'status': overall_status,
            'temp': overall_temp,
            'dryers': all_dryers,  # NEW: All dryers array (replaces single dryer_status)
            'gate_color': all_gate_colors,
            'gate_material': all_gate_materials,
            'gate_temp': all_gate_temps,
            'active_gate': all_active_gates,
            'spool_id': all_spool_ids,
            'selected_gate': selected_gate,
            'endless_spool': endless_spool,
            'num_gates': self.total_gates,
            'num_devices': len(self.ace_devices),
            'devices': devices_summary,
            'devices_detail': devices_detail,
        }

    def get_device_list(self):
        """
        Get list of all ACE devices with detailed status and health metrics.
        Used by Moonraker API for /printer/ace/devices endpoint.
        """
        devices = []

        for dev in self.ace_devices:
            ace = dev['instance']
            device_info = {
                'device_id': dev.get('device_id', f"unknown_{dev['port']}"),
                'name': dev.get('name', f"ACE Unit {dev['gate_offset']//4 + 1}"),
                'port': dev.get('port', 'Unknown'),
                'model': dev.get('model', 'Unknown'),
                'firmware': dev.get('firmware', 'Unknown'),
                'connection_status': 'connected' if ace._connected else 'disconnected',
                'gate_offset': dev['gate_offset'],
                'num_gates': 4,
                'gates': list(range(dev['gate_offset'], dev['gate_offset'] + 4)),
                'last_seen': dev.get('last_seen', 0),
                'health': self._get_device_health(ace)
            }
            devices.append(device_info)

        return {
            'devices': devices,
            'total_gates': self.total_gates,
            'auto_detect_enabled': self.config.getboolean('auto_detect', False),
            'device_map_file': getattr(self, 'device_mapper', None) and
                              getattr(self.device_mapper, 'config_path', None) or 'N/A'
        }

    def _get_device_health(self, ace_instance):
        """
        Get health metrics for an ACE device instance.
        Returns: dict with health statistics
        """
        # Default health metrics
        health = {
            'avg_response_time_ms': 0,
            'error_count': 0,
            'last_error': None,
            'uptime': 0
        }

        # Try to get actual health stats if the ACE instance tracks them
        if hasattr(ace_instance, 'health_stats'):
            health.update(ace_instance.health_stats)

        # Calculate uptime if available
        if hasattr(ace_instance, 'connect_time'):
            health['uptime'] = int(time.time() - ace_instance.connect_time)

        return health

    def scan_devices(self, rescan=True, update_map=True):
        """
        Manually trigger device scan.
        Used by Moonraker API for /printer/ace/scan endpoint.

        Args:
            rescan: If True, re-scan USB ports. If False, just return current devices.
            update_map: If True, update device map file with new devices.

        Returns: dict with scan results
        """
        if not rescan:
            return {
                'status': 'success',
                'devices_found': len(self.ace_devices),
                'new_devices': 0,
                'devices': self.get_device_list()
            }

        # Re-run auto-detection
        logging.info("ACE Manager: Manual device scan requested")
        discovered = AceDeviceDiscovery.find_ace_devices()
        new_devices = []

        for dev_info in discovered:
            port = dev_info['port']
            ace_info = AceDeviceDiscovery.probe_ace_device(port)

            if ace_info:
                device_id = ace_info['device_id']
                # Check if this is a new device
                existing_ids = [d.get('device_id') for d in self.ace_devices]
                if device_id not in existing_ids:
                    new_devices.append({
                        'device_id': device_id,
                        'port': port,
                        'model': ace_info.get('model', 'Unknown'),
                        'firmware': ace_info.get('firmware', 'Unknown')
                    })
                    logging.info(f"ACE Manager: Found new ACE device: {device_id} at {port}")

        # Update device map if requested and new devices found
        if update_map and new_devices and hasattr(self, 'device_mapper'):
            try:
                self.device_mapper.save()
                logging.info("ACE Manager: Device map updated")
            except Exception as e:
                logging.error(f"ACE Manager: Failed to update device map: {e}")

        return {
            'status': 'success',
            'devices_found': len(discovered),
            'new_devices': len(new_devices),
            'new_device_list': new_devices,
            'devices': self.get_device_list()
        }

    def _reenumerate_devices(self):
        """
        Shared enumeration logic for both boot-time and runtime device discovery.

        Scans USB ports, probes ACE devices, sorts by USB location, calculates gate offsets,
        and compares with current configuration.

        Returns:
            dict: Enumeration plan containing:
                - current_devices: Current ace_devices list
                - discovered_devices: Newly scanned devices (sorted by USB location)
                - added: List of devices to add (not in current config)
                - removed: List of devices to remove (missing from scan)
                - reordered: List of devices with changed gate offsets
                - unchanged: List of devices staying the same
                - gate_offset_map: Dict mapping device_id -> new gate offset
        """
        logging.info("ACE Manager: Starting device re-enumeration...")

        # Get current configuration
        current_devices = self.ace_devices if hasattr(self, 'ace_devices') else []
        current_device_ids = {d.get('device_id'): d for d in current_devices}

        # Discover all ACE devices on USB ports
        discovered = AceDeviceDiscovery.find_ace_devices()

        if not discovered:
            logging.warning("ACE Manager: No ACE devices found during re-enumeration")
            return {
                'current_devices': current_devices,
                'discovered_devices': [],
                'added': [],
                'removed': list(current_devices),
                'reordered': [],
                'unchanged': [],
                'gate_offset_map': {}
            }

        # Probe and verify each discovered device
        verified_devices = []
        for device_info in discovered:
            port = device_info.get('port')
            usb_location = device_info.get('location')

            if not port:
                continue

            try:
                # Probe the device
                probe_result = AceDeviceDiscovery.probe_ace_device(port, baud=self.baud, usb_location=usb_location)
                if probe_result:
                    device_id = probe_result['device_id']

                    verified_devices.append({
                        'device_id': device_id,
                        'port': port,
                        'usb_location': usb_location or '',
                        'firmware_version': probe_result.get('firmware', 'unknown'),
                        'model': probe_result.get('model', 'ACE'),
                        'device_info': device_info,
                        'probe_result': probe_result
                    })
                    logging.info(f"ACE Manager: Verified device {device_id} at {port}")
            except Exception as e:
                logging.error(f"ACE Manager: Failed to probe device at {port}: {e}")

        if not verified_devices:
            logging.error("ACE Manager: No ACE devices could be verified")
            return {
                'current_devices': current_devices,
                'discovered_devices': [],
                'added': [],
                'removed': list(current_devices),
                'reordered': [],
                'unchanged': [],
                'gate_offset_map': {}
            }

        # Sort devices by USB location for deterministic ordering
        verified_devices.sort(key=lambda d: d.get('usb_location', ''))

        # Calculate new gate offsets (continuous: 0-3, 4-7, 8-11...)
        gate_offset_map = {}
        for i, dev in enumerate(verified_devices):
            gate_offset_map[dev['device_id']] = i * 4

        # Analyze changes
        discovered_device_ids = {d['device_id']: d for d in verified_devices}

        added = []
        removed = []
        reordered = []
        unchanged = []

        # Find added devices (in discovered, not in current)
        for device_id, dev in discovered_device_ids.items():
            if device_id not in current_device_ids:
                added.append({
                    'device_id': device_id,
                    'port': dev['port'],
                    'usb_location': dev['usb_location'],
                    'gate_offset': gate_offset_map[device_id],
                    'gates': f"{gate_offset_map[device_id]}-{gate_offset_map[device_id]+3}"
                })

        # Find removed devices (in current, not in discovered)
        for device_id, dev in current_device_ids.items():
            if device_id not in discovered_device_ids:
                removed.append({
                    'device_id': device_id,
                    'port': dev.get('port', 'unknown'),
                    'gate_offset': dev.get('gate_offset', -1),
                    'gates': f"{dev.get('gate_offset', -1)}-{dev.get('gate_offset', -1)+3}"
                })

        # Find reordered devices (gate offset changed)
        for device_id, dev in discovered_device_ids.items():
            if device_id in current_device_ids:
                old_offset = current_device_ids[device_id].get('gate_offset', -1)
                new_offset = gate_offset_map[device_id]

                if old_offset != new_offset:
                    reordered.append({
                        'device_id': device_id,
                        'port': dev['port'],
                        'usb_location': dev['usb_location'],
                        'old_gate_offset': old_offset,
                        'new_gate_offset': new_offset,
                        'old_gates': f"{old_offset}-{old_offset+3}",
                        'new_gates': f"{new_offset}-{new_offset+3}"
                    })
                else:
                    unchanged.append({
                        'device_id': device_id,
                        'port': dev['port'],
                        'usb_location': dev['usb_location'],
                        'gate_offset': new_offset,
                        'gates': f"{new_offset}-{new_offset+3}"
                    })

        logging.info(f"ACE Manager: Enumeration complete - Added: {len(added)}, "
                    f"Removed: {len(removed)}, Reordered: {len(reordered)}, "
                    f"Unchanged: {len(unchanged)}")

        return {
            'current_devices': current_devices,
            'discovered_devices': verified_devices,
            'added': added,
            'removed': removed,
            'reordered': reordered,
            'unchanged': unchanged,
            'gate_offset_map': gate_offset_map
        }

    def _check_enumeration_safety(self):
        """
        Check if it's safe to apply device enumeration (hot-reload).

        Returns:
            tuple: (bool is_safe, str reason)
        """
        # Check if printer is printing
        try:
            idle_timeout = self.printer.lookup_object('idle_timeout')
            if hasattr(idle_timeout, 'state'):
                if idle_timeout.state == "Printing":
                    return False, "Cannot re-enumerate during active print"
        except:
            pass

        # Check print_stats for printing state
        try:
            print_stats = self.printer.lookup_object('print_stats')
            if hasattr(print_stats, 'state'):
                if print_stats.state in ['printing', 'paused']:
                    return False, f"Cannot re-enumerate while print is {print_stats.state}"
        except:
            pass

        # Check if any ACE device has filament loaded
        for device in self.ace_devices:
            ace_instance = device.get('instance')
            if ace_instance:
                try:
                    status = ace_instance.get_status()

                    # Check if filament is detected at extruder sensor
                    if hasattr(ace_instance, 'extruder_sensor'):
                        if ace_instance.extruder_sensor.last_state == 1:  # Filament detected
                            device_id = device.get('device_id', 'unknown')
                            return False, f"Cannot re-enumerate with filament loaded (detected on {device_id})"

                    # Check if filament is detected at toolhead sensor
                    if hasattr(ace_instance, 'toolhead_sensor'):
                        if ace_instance.toolhead_sensor.last_state == 1:  # Filament detected
                            device_id = device.get('device_id', 'unknown')
                            return False, f"Cannot re-enumerate with filament in toolhead (detected on {device_id})"

                    # Check current_index (loaded gate)
                    if status.get('current_index', -1) >= 0:
                        device_id = device.get('device_id', 'unknown')
                        gate = status.get('current_index', -1)
                        return False, f"Cannot re-enumerate with active gate (gate {gate} on {device_id})"

                except Exception as e:
                    logging.warning(f"ACE Manager: Error checking device safety: {e}")

        return True, "Safe to re-enumerate"

    def _apply_device_enumeration(self, enum_plan):
        """
        Apply device enumeration plan and reconfigure ACE devices at runtime.

        This method performs a hot-reload of the ACE device configuration without
        requiring a Klipper restart.

        Args:
            enum_plan: Dict returned by _reenumerate_devices()

        Returns:
            dict: Result of the operation with status and changes applied

        Raises:
            Exception: If enumeration cannot be safely applied
        """
        logging.info("ACE Manager: Applying device enumeration changes...")

        # Safety check
        is_safe, reason = self._check_enumeration_safety()
        if not is_safe:
            raise Exception(f"Safety check failed: {reason}")

        discovered_devices = enum_plan['discovered_devices']
        added = enum_plan['added']
        removed = enum_plan['removed']
        reordered = enum_plan['reordered']
        gate_offset_map = enum_plan['gate_offset_map']

        if not discovered_devices:
            raise Exception("No devices discovered - cannot apply empty configuration")

        # Step 1: Shut down all current ACE instances
        logging.info("ACE Manager: Shutting down current ACE instances...")
        for device in self.ace_devices:
            ace_instance = device.get('instance')
            if ace_instance:
                try:
                    # Disconnect serial connection
                    if hasattr(ace_instance, 'serial') and ace_instance.serial:
                        ace_instance.serial.close()
                        logging.info(f"ACE Manager: Closed serial connection for {device.get('device_id')}")
                except Exception as e:
                    logging.warning(f"ACE Manager: Error closing serial for {device.get('device_id')}: {e}")

        # Step 2: Clear current device list
        old_device_count = len(self.ace_devices)
        self.ace_devices.clear()

        # Step 3: Create new ACE instances from discovered devices
        logging.info(f"ACE Manager: Creating {len(discovered_devices)} new ACE instances...")

        for i, dev in enumerate(discovered_devices):
            device_id = dev['device_id']
            port = dev['port']
            gate_offset = gate_offset_map[device_id]

            try:
                # Create ACE configuration on the fly
                ace_config = {
                    'serial': port,
                    'baud': self.baud,
                    'extruder_sensor_pin': self.extruder_sensor_pin,
                    'toolhead_sensor_pin': self.toolhead_sensor_pin,
                    'extruder_move_speed': self.extruder_move_speed,
                    'toolhead_homing_speed': self.toolhead_homing_speed,
                    'feed_speed': self.feed_speed,
                    'retract_speed': self.retract_speed,
                    'toolchange_retract_length': self.toolchange_retract_length,
                    'toolchange_feed_length': self.toolchange_feed_length,
                    'toolhead_sensor_to_nozzle': self.toolhead_sensor_to_nozzle,
                    'poop_macros': self.poop_macros,
                    'cut_macros': self.cut_macros,
                    'max_dryer_temperature': self.max_dryer_temperature,
                    'gate_offset': gate_offset
                }

                # Create config wrapper (similar to _setup_from_serial_ports)
                ace_name = f"ACE_{i+1}"

                class AceConfigWrapper:
                    def __init__(self, printer, name, ace_config, parent_config):
                        self.printer = printer
                        self.name = name
                        self.ace_config = ace_config
                        self.parent_config = parent_config

                    def get_printer(self):
                        return self.printer

                    def get_name(self):
                        return self.name

                    def getsection(self, section):
                        class FileconfigSectionWrapper:
                            def __init__(self, ace_wrapper, section):
                                self.ace_wrapper = ace_wrapper
                                self.section = section

                            def get(self, key, default=None):
                                if key in self.ace_wrapper.ace_config:
                                    return self.ace_wrapper.ace_config[key]
                                if self.ace_wrapper.parent_config:
                                    return self.ace_wrapper.parent_config.get(key, default)
                                return default

                            def getint(self, key, default=None):
                                val = self.get(key, default)
                                if val is None:
                                    return default
                                return int(val)

                            def getfloat(self, key, default=None):
                                val = self.get(key, default)
                                if val is None:
                                    return default
                                return float(val)

                            def getboolean(self, key, default=None):
                                val = self.get(key, default)
                                if val is None:
                                    return default
                                if isinstance(val, bool):
                                    return val
                                return str(val).lower() in ('true', '1', 'yes')

                            def getlist(self, key, default=None):
                                val = self.get(key, default)
                                if val is None:
                                    if default is None:
                                        return []
                                    return default
                                if isinstance(val, list):
                                    return val
                                return [item.strip() for item in str(val).split(',') if item.strip()]

                            def getsection(self, section):
                                return self

                            def error(self, msg):
                                raise Exception(msg)

                        return FileconfigSectionWrapper(self, section)

                    def error(self, msg):
                        raise Exception(msg)

                # Create ACE instance
                config_wrapper = AceConfigWrapper(self.printer, f"ace {ace_name}", ace_config, None)
                ace_instance = BunnyAce(config_wrapper)

                # Store device info
                self.ace_devices.append({
                    'name': ace_name,
                    'port': port,
                    'instance': ace_instance,
                    'gate_offset': gate_offset,
                    'device_id': device_id
                })

                # Update device IDs mapping
                if not hasattr(self, 'device_ids'):
                    self.device_ids = {}
                self.device_ids[port] = device_id

                logging.info(f"ACE Manager: Created {ace_name} (ID: {device_id}) on {port} with gate offset {gate_offset}")

            except Exception as e:
                logging.error(f"ACE Manager: Failed to create ACE instance for {device_id}: {e}")
                raise Exception(f"Failed to create ACE instance for {device_id}: {e}")

        # Step 4: Update total gates
        self.total_gates = len(self.ace_devices) * 4

        # Step 5: Update device mapper
        if hasattr(self, 'device_mapper') and self.device_mapper:
            for dev in discovered_devices:
                device_id = dev['device_id']
                port = dev['port']
                usb_location = dev.get('usb_location', '')
                gate_offset = gate_offset_map[device_id]

                self.device_mapper.update_device(device_id, port, usb_location, gate_offset)

            # Migrate device properties to new instances
            self._migrate_device_properties_to_ace_instances()

            # Save device map
            try:
                self.device_mapper.save()
                logging.info("ACE Manager: Device map updated and saved")
            except Exception as e:
                logging.error(f"ACE Manager: Failed to save device map: {e}")

        # Update verified devices for consistency
        self._verified_devices = discovered_devices

        logging.info(f"ACE Manager: Hot-reload complete - {old_device_count} → {len(self.ace_devices)} devices, {self.total_gates} gates")

        return {
            'status': 'success',
            'old_device_count': old_device_count,
            'new_device_count': len(self.ace_devices),
            'total_gates': self.total_gates,
            'added': added,
            'removed': removed,
            'reordered': reordered
        }

    def reorder_gates(self, device_order):
        """
        Reorder gate assignments for devices.
        Used by Moonraker API for /printer/ace/reorder endpoint.

        Args:
            device_order: List of dicts with 'device_id' and 'gate_offset' keys

        Returns: dict with status
        """
        # Validate new order
        device_ids = [d['device_id'] for d in device_order]
        current_ids = [d.get('device_id') for d in self.ace_devices]

        if set(device_ids) != set(current_ids):
            raise Exception("Device order must include all current devices")

        # Validate that gate offsets are multiples of 4 and don't overlap
        offsets = [d['gate_offset'] for d in device_order]
        for offset in offsets:
            if offset % 4 != 0:
                raise Exception(f"Gate offset {offset} must be a multiple of 4")

        # Check for overlaps
        if len(offsets) != len(set(offsets)):
            raise Exception("Gate offsets must be unique")

        # Update device map if available
        if hasattr(self, 'device_mapper'):
            for order_info in device_order:
                device_id = order_info['device_id']
                new_offset = order_info['gate_offset']

                # Find the device in our list
                for dev in self.ace_devices:
                    if dev.get('device_id') == device_id:
                        # Update the device mapper
                        self.device_mapper.update_device(device_id, dev.get('port'), new_offset)
                        break

            try:
                self.device_mapper.save()
                logging.info("ACE Manager: Device order updated successfully")
            except Exception as e:
                logging.error(f"ACE Manager: Failed to save device order: {e}")
                raise Exception(f"Failed to save device order: {e}")
        else:
            logging.warning("ACE Manager: Device mapper not available, cannot persist order changes")

        return {
            'status': 'success',
            'message': 'Gate assignments updated. Restart Klipper to apply changes.',
            'restart_required': True
        }

    cmd_ACE_GET_STATUS_help = 'Get unified status from all ACE devices'

    def cmd_ACE_GET_STATUS(self, gcmd):
        """Display aggregated status from all ACE units"""
        self.gcode.respond_info('=== ACE Manager Status ===')
        self.gcode.respond_info(f'Total Gates: {self.total_gates}')
        self.gcode.respond_info(f'ACE Devices: {len(self.ace_devices)}')

        all_slots = []
        for device in self.ace_devices:
            ace = device['instance']
            offset = device['gate_offset']

            self.gcode.respond_info(f"\n--- {device['name']} (gates {offset}-{offset+3}) ---")

            # Get status from this ACE
            status = ace.get_status()

            # Display this ACE's slots with global gate numbers
            for i, slot_status in enumerate(status['active_gate']):
                global_gate = offset + i
                material = status['gate_material'][i] if i < len(status['gate_material']) else ''
                color = status['gate_color'][i] if i < len(status['gate_color']) else 'FFFFFF'

                self.gcode.respond_info(
                    f"  Gate {global_gate}: {slot_status} | Type: {material} | Color: {color}"
                )

    cmd_ACE_FEED_help = 'Feed filament (unified across all ACE devices)'

    def cmd_ACE_FEED(self, gcmd):
        """Unified feed command"""
        gate = gcmd.get_int('INDEX')
        ace_instance, local_gate = self._route_to_ace(gate)

        # Create modified gcmd with local gate
        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', ace_instance.feed_speed)

        ace_instance._feed(local_gate, length, speed)

    cmd_ACE_RETRACT_help = 'Retract filament (unified across all ACE devices)'

    def cmd_ACE_RETRACT(self, gcmd):
        """Unified retract command"""
        gate = gcmd.get_int('INDEX')
        ace_instance, local_gate = self._route_to_ace(gate)

        length = gcmd.get_int('LENGTH')
        speed = gcmd.get_int('SPEED', ace_instance.retract_speed)

        ace_instance._retract(local_gate, length, speed)

    cmd_ACE_GATE_MAP_help = 'Set gate info (unified across all ACE devices)'

    def cmd_ACE_GATE_MAP(self, gcmd):
        """Unified gate mapping with device-specific variable storage"""
        gate = gcmd.get_int('GATE')
        ace_instance, local_gate = self._route_to_ace(gate)

        # Find the device_id for this ACE instance
        device_id = None
        for dev in self.ace_devices:
            if dev['instance'] == ace_instance:
                device_id = dev.get('device_id', f"dev_{dev['gate_offset']}")
                break

        if not device_id:
            self.gcode.respond_info("Error: Could not identify device")
            logging.error(f"ACE Manager: Could not find device_id for gate {gate}")
            return

        # Use device-specific variable names to avoid cross-contamination
        color = gcmd.get('COLOR', None)
        type_param = gcmd.get('TYPE', None)
        temp = gcmd.get_int('TEMP', None)

        # Update device properties in device mapper (persistent storage)
        if hasattr(self, 'device_mapper') and self.device_mapper:
            device_props = self.device_mapper.get_device_properties(device_id)
            if not device_props:
                device_props = {
                    'gate_colors': ['FFFFFF'] * 4,
                    'gate_materials': [''] * 4,
                    'gate_temps': [230] * 4
                }

            if color:
                if 'gate_colors' not in device_props:
                    device_props['gate_colors'] = ['FFFFFF'] * 4
                device_props['gate_colors'][local_gate] = color

            if type_param:
                if 'gate_materials' not in device_props:
                    device_props['gate_materials'] = [''] * 4
                device_props['gate_materials'][local_gate] = type_param

            if temp:
                if 'gate_temps' not in device_props:
                    device_props['gate_temps'] = [230] * 4
                device_props['gate_temps'][local_gate] = temp

            self.device_mapper.update_device_properties(device_id, device_props)
            self.device_mapper.save()

            # Also update the ACE instance's in-memory state
            if color and hasattr(ace_instance, 'save_variables'):
                ace_instance.save_variables.allVariables.setdefault('ace_gate_color', ['FFFFFF'] * 4)[local_gate] = color
            if type_param and hasattr(ace_instance, 'save_variables'):
                ace_instance.save_variables.allVariables.setdefault('ace_gate_type', [''] * 4)[local_gate] = type_param
            if temp and hasattr(ace_instance, 'save_variables'):
                ace_instance.save_variables.allVariables.setdefault('ace_gate_temp', [230] * 4)[local_gate] = temp

            if (color or type_param or temp) and hasattr(ace_instance, 'write_variables'):
                ace_instance.write_variables()

            logging.info(f"ACE Manager: Updated gate {gate} on device {device_id} (local gate {local_gate})")
        else:
            # Fallback to old method if device mapper not available
            if color:
                ace_instance.save_variables.allVariables.setdefault('ace_gate_color', ['FFFFFF'] * 4)[local_gate] = color
            if type_param:
                ace_instance.save_variables.allVariables.setdefault('ace_gate_type', [''] * 4)[local_gate] = type_param
            if temp:
                ace_instance.save_variables.allVariables.setdefault('ace_gate_temp', [230] * 4)[local_gate] = temp

            if color or type_param or temp:
                ace_instance.write_variables()
                logging.info(f"ACE Manager: Updated gate {gate} (local gate {local_gate})")

    cmd_ACE_SCAN_DEVICES_help = 'Scan for ACE devices and optionally apply changes (use APPLY=1 to hot-reload)'

    def cmd_ACE_SCAN_DEVICES(self, gcmd):
        """
        Scan for ACE devices and report findings.
        Use APPLY=1 to apply changes and hot-reload device configuration.
        """
        apply_changes = gcmd.get_int('APPLY', 0) == 1

        self.gcode.respond_info('=' * 70)
        self.gcode.respond_info('ACE Device Scan & Enumeration')
        self.gcode.respond_info('=' * 70)
        self.gcode.respond_info('Scanning USB ports for ACE devices...')

        # Run enumeration
        try:
            enum_plan = self._reenumerate_devices()
        except Exception as e:
            self.gcode.respond_info(f"ERROR: Scan failed: {e}")
            return

        current_devices = enum_plan['current_devices']
        discovered_devices = enum_plan['discovered_devices']
        added = enum_plan['added']
        removed = enum_plan['removed']
        reordered = enum_plan['reordered']
        unchanged = enum_plan['unchanged']

        # Report scan results
        self.gcode.respond_info(f"\nScan Results:")
        self.gcode.respond_info(f"  Devices currently configured: {len(current_devices)}")
        self.gcode.respond_info(f"  Devices discovered on USB:    {len(discovered_devices)}")

        if not discovered_devices:
            self.gcode.respond_info("\n⚠ WARNING: No ACE devices found!")
            self.gcode.respond_info("Check USB connections and power.")
            return

        # Show detailed change analysis
        has_changes = len(added) > 0 or len(removed) > 0 or len(reordered) > 0

        if not has_changes:
            self.gcode.respond_info("\n✓ No configuration changes detected")
            self.gcode.respond_info(f"  All {len(unchanged)} device(s) unchanged")
        else:
            self.gcode.respond_info("\n⚠ Configuration changes detected:")

            if added:
                self.gcode.respond_info(f"\n  ➕ Devices to ADD ({len(added)}):")
                for dev in added:
                    self.gcode.respond_info(f"     • {dev['device_id']}")
                    self.gcode.respond_info(f"       Port: {dev['port']}")
                    self.gcode.respond_info(f"       USB:  {dev['usb_location']}")
                    self.gcode.respond_info(f"       Gates: {dev['gates']}")

            if removed:
                self.gcode.respond_info(f"\n  ➖ Devices to REMOVE ({len(removed)}):")
                for dev in removed:
                    self.gcode.respond_info(f"     • {dev['device_id']}")
                    self.gcode.respond_info(f"       Was on port: {dev['port']}")
                    self.gcode.respond_info(f"       Was gates: {dev['gates']}")

            if reordered:
                self.gcode.respond_info(f"\n  🔄 Devices with CHANGED gate offsets ({len(reordered)}):")
                for dev in reordered:
                    self.gcode.respond_info(f"     • {dev['device_id']}")
                    self.gcode.respond_info(f"       Port: {dev['port']}")
                    self.gcode.respond_info(f"       USB:  {dev['usb_location']}")
                    self.gcode.respond_info(f"       Gates: {dev['old_gates']} → {dev['new_gates']}")

            if unchanged:
                self.gcode.respond_info(f"\n  ✓ Devices UNCHANGED ({len(unchanged)}):")
                for dev in unchanged:
                    self.gcode.respond_info(f"     • {dev['device_id']} - Gates {dev['gates']}")

        # Show discovered devices summary
        self.gcode.respond_info("\n" + "-" * 70)
        self.gcode.respond_info("Discovered Device Configuration:")
        self.gcode.respond_info("-" * 70)
        for i, dev in enumerate(discovered_devices):
            device_id = dev['device_id']
            port = dev['port']
            usb_location = dev.get('usb_location', 'N/A')
            gate_offset = enum_plan['gate_offset_map'][device_id]
            gates_str = f"{gate_offset}-{gate_offset+3}"

            self.gcode.respond_info(f"\nDevice {i+1}: {device_id}")
            self.gcode.respond_info(f"  Port:      {port}")
            self.gcode.respond_info(f"  USB:       {usb_location}")
            self.gcode.respond_info(f"  Gates:     {gates_str}")
            self.gcode.respond_info(f"  Firmware:  {dev.get('firmware_version', 'unknown')}")

        # Apply changes if requested
        if apply_changes:
            if not has_changes:
                self.gcode.respond_info("\n" + "=" * 70)
                self.gcode.respond_info("ℹ No changes to apply - configuration already up to date")
                self.gcode.respond_info("=" * 70)
                return

            self.gcode.respond_info("\n" + "=" * 70)
            self.gcode.respond_info("APPLY=1 detected - Attempting hot-reload...")
            self.gcode.respond_info("=" * 70)

            # Check safety
            is_safe, reason = self._check_enumeration_safety()
            if not is_safe:
                self.gcode.respond_info(f"\n❌ SAFETY CHECK FAILED: {reason}")
                self.gcode.respond_info("\nCannot apply changes. Please:")
                self.gcode.respond_info("  1. Ensure no print is active")
                self.gcode.respond_info("  2. Unload all filament")
                self.gcode.respond_info("  3. Try again with ACE_SCAN_DEVICES APPLY=1")
                return

            # Apply the enumeration
            try:
                result = self._apply_device_enumeration(enum_plan)
                self.gcode.respond_info("\n✅ Hot-reload SUCCESSFUL!")
                self.gcode.respond_info(f"   Devices: {result['old_device_count']} → {result['new_device_count']}")
                self.gcode.respond_info(f"   Gates:   {result['total_gates']}")
                self.gcode.respond_info("\nDevice configuration updated without restart!")
            except Exception as e:
                self.gcode.respond_info(f"\n❌ Hot-reload FAILED: {e}")
                self.gcode.respond_info("\nKlipper restart required to recover.")
                self.gcode.respond_info("Run: RESTART")

        else:
            # Not applying - show instructions
            if has_changes:
                self.gcode.respond_info("\n" + "=" * 70)
                self.gcode.respond_info("ℹ Preview mode - no changes applied")
                self.gcode.respond_info("=" * 70)
                self.gcode.respond_info("\nTo apply these changes:")
                self.gcode.respond_info("  Option 1: ACE_SCAN_DEVICES APPLY=1  (hot-reload, no restart)")
                self.gcode.respond_info("  Option 2: RESTART                    (full Klipper restart)")
                self.gcode.respond_info("\nHot-reload safety requirements:")
                self.gcode.respond_info("  • No active print")
                self.gcode.respond_info("  • All filament unloaded")
            else:
                self.gcode.respond_info("\n" + "=" * 70)

    cmd_ACE_LIST_DEVICES_help = 'List all ACE devices with status'

    def cmd_ACE_LIST_DEVICES(self, gcmd):
        """List all ACE devices"""
        devices = self.get_device_list()

        self.gcode.respond_info(f"=== ACE Devices ({devices['total_gates']} gates) ===")
        self.gcode.respond_info(f"Auto-detect: {'enabled' if devices['auto_detect_enabled'] else 'disabled'}")

        for dev in devices['devices']:
            status_icon = "✓" if dev['connection_status'] == 'connected' else "✗"
            gates_str = f"{dev['gates'][0]}-{dev['gates'][-1]}"

            self.gcode.respond_info(f"\n{status_icon} {dev['name']}: {dev['model']} v{dev['firmware']}")
            self.gcode.respond_info(f"   Port: {dev['port']}")
            self.gcode.respond_info(f"   Gates: {gates_str}")
            self.gcode.respond_info(f"   Status: {dev['connection_status']}")

            # Show health metrics if available
            health = dev.get('health', {})
            if health.get('uptime'):
                uptime_hours = health['uptime'] // 3600
                uptime_mins = (health['uptime'] % 3600) // 60
                self.gcode.respond_info(f"   Uptime: {uptime_hours}h {uptime_mins}m")
            if health.get('error_count') is not None:
                self.gcode.respond_info(f"   Errors: {health['error_count']}")

    cmd_ACE_SHOW_USB_INFO_help = 'Show USB topology and device mapping information'

    def cmd_ACE_SHOW_USB_INFO(self, gcmd):
        """Show detailed USB port location and device mapping information"""
        self.gcode.respond_info("=" * 70)
        self.gcode.respond_info("ACE USB Port Mapping & Device Topology")
        self.gcode.respond_info("=" * 70)

        if not hasattr(self, 'device_mapper') or not self.device_mapper:
            self.gcode.respond_info("Device mapper not initialized (auto_detect not enabled)")
            return

        # Get all known devices from mapper
        all_devices = self.device_mapper.get_all_devices()

        # Show currently connected devices
        self.gcode.respond_info("\nCurrently Connected Devices:")
        self.gcode.respond_info("-" * 70)

        for i, ace_device in enumerate(self.ace_devices):
            device_id = ace_device.get('device_id', 'unknown')
            port = ace_device.get('port', 'unknown')
            gate_offset = ace_device.get('gate_offset', 0)
            gates_str = f"{gate_offset}-{gate_offset + 3}"

            device_info = self.device_mapper.get_device_info(device_id)
            usb_location = device_info.get('usb_location', 'N/A') if device_info else 'N/A'

            # Determine device ID type
            id_type = "Unknown"
            id_quality = "⚠"
            if device_id.startswith('mac_'):
                id_type = "MAC Address"
                id_quality = "✓"
            elif device_id.startswith('sn_'):
                id_type = "Serial Number"
                id_quality = "✓"
            elif device_id.startswith('hub_') or device_id.startswith('usb_'):
                id_type = "USB Location"
                id_quality = "✓"
            elif device_id.startswith('fw_'):
                id_type = "Firmware Hash"
                id_quality = "❌"

            self.gcode.respond_info(f"\n{id_quality} Device {i+1}: {device_id}")
            self.gcode.respond_info(f"   ID Type:      {id_type}")
            self.gcode.respond_info(f"   USB Location: {usb_location}")
            self.gcode.respond_info(f"   Serial Port:  {port}")
            self.gcode.respond_info(f"   Gate Range:   {gates_str}")

            # Show dryer status
            ace_instance = ace_device.get('instance')
            if ace_instance:
                status = ace_instance.get_status()
                dryer = status.get('dryer_status', {})
                dryer_status = dryer.get('status', 'unknown')
                temp = status.get('temp', 0)
                target_temp = dryer.get('target_temp', 0)
                remain_time = dryer.get('remain_time', 0)

                if dryer_status == 'running':
                    self.gcode.respond_info(f"   Dryer:        🔥 Running ({temp}°C → {target_temp}°C, {remain_time}min remaining)")
                else:
                    self.gcode.respond_info(f"   Dryer:        ⭘ Stopped ({temp}°C)")

            # Show device properties if available
            if device_info and 'properties' in device_info:
                props = device_info['properties']
                if props.get('gate_materials'):
                    materials_str = ', '.join([m or 'None' for m in props['gate_materials']])
                    self.gcode.respond_info(f"   Materials:    [{materials_str}]")
                if props.get('gate_colors'):
                    colors_str = ', '.join([c or 'FFFFFF' for c in props['gate_colors']])
                    self.gcode.respond_info(f"   Colors:       [{colors_str}]")

        # Show historical/disconnected devices
        disconnected_devices = []
        for device_id, info in all_devices.items():
            # Check if this device is currently connected
            is_connected = any(d.get('device_id') == device_id for d in self.ace_devices)
            if not is_connected:
                disconnected_devices.append((device_id, info))

        if disconnected_devices:
            self.gcode.respond_info("\n" + "=" * 70)
            self.gcode.respond_info("Previously Seen Devices (Not Currently Connected):")
            self.gcode.respond_info("-" * 70)

            for device_id, info in disconnected_devices:
                usb_location = info.get('usb_location', 'N/A')
                last_port = info.get('port', 'unknown')
                last_gate_offset = info.get('last_gate_offset', 0)
                last_seen = info.get('last_seen', 0)

                import time
                if last_seen > 0:
                    time_diff = int(time.time()) - last_seen
                    if time_diff < 60:
                        time_ago = f"{time_diff}s ago"
                    elif time_diff < 3600:
                        time_ago = f"{time_diff // 60}m ago"
                    elif time_diff < 86400:
                        time_ago = f"{time_diff // 3600}h ago"
                    else:
                        time_ago = f"{time_diff // 86400}d ago"
                else:
                    time_ago = "unknown"

                self.gcode.respond_info(f"\n⊗ Device: {device_id}")
                self.gcode.respond_info(f"   USB Location:    {usb_location}")
                self.gcode.respond_info(f"   Last Port:       {last_port}")
                self.gcode.respond_info(f"   Last Gate Offset: {last_gate_offset}-{last_gate_offset + 3}")
                self.gcode.respond_info(f"   Last Seen:       {time_ago}")

        # Show summary
        self.gcode.respond_info("\n" + "=" * 70)
        self.gcode.respond_info("Summary:")
        self.gcode.respond_info("-" * 70)
        self.gcode.respond_info(f"Total Connected Devices:  {len(self.ace_devices)}")
        self.gcode.respond_info(f"Total Gates Available:    {self.total_gates}")
        self.gcode.respond_info(f"Known Devices (Total):    {len(all_devices)}")
        self.gcode.respond_info(f"Disconnected Devices:     {len(disconnected_devices)}")

        # Show warnings if using firmware hash IDs
        firmware_hash_devices = [d for d in self.ace_devices if d.get('device_id', '').startswith('fw_')]
        if firmware_hash_devices:
            self.gcode.respond_info("\n⚠ WARNING: Some devices are using firmware hash IDs")
            self.gcode.respond_info("   This is not reliable for multiple identical devices.")
            self.gcode.respond_info("   Consider using a USB hub to enable USB location-based IDs.")

        # Suggest scanning if there are disconnected devices
        if disconnected_devices:
            self.gcode.respond_info("\nℹ TIP: Devices may have changed. To scan and update:")
            self.gcode.respond_info("   ACE_SCAN_DEVICES        - Preview changes")
            self.gcode.respond_info("   ACE_SCAN_DEVICES APPLY=1 - Apply changes (hot-reload)")

        self.gcode.respond_info("\n" + "=" * 70)
        self.gcode.respond_info("Device properties (colors, materials, temps) persist with each device")
        self.gcode.respond_info("Gate offsets are dynamically assigned based on connected device order")
        self.gcode.respond_info("\nHot-plug support:")
        self.gcode.respond_info("  • Run ACE_SCAN_DEVICES to detect device changes")
        self.gcode.respond_info("  • Use APPLY=1 to hot-reload configuration without restart")
        self.gcode.respond_info("=" * 70)

    cmd_ACE_REORDER_DEVICES_help = 'Reorder ACE device gate assignments'

    def cmd_ACE_REORDER_DEVICES(self, gcmd):
        """Reorder ACE device gate assignments (for Moonraker API)"""
        # Get the ORDER parameter (JSON string)
        order_str = gcmd.get('ORDER', None)

        if not order_str:
            self.gcode.respond_info('Error: ORDER parameter required')
            self.gcode.respond_info('Usage: ACE_REORDER_DEVICES ORDER=\'[{"device_id": "...", "gate_offset": 0}, ...]\'')
            return

        try:
            import json
            device_order = json.loads(order_str)

            # Call the reorder_gates method
            result = self.reorder_gates(device_order)

            self.gcode.respond_info('=== ACE Device Reorder ===')
            self.gcode.respond_info(f"Status: {result['status']}")
            self.gcode.respond_info(f"Message: {result['message']}")

            if result.get('restart_required'):
                self.gcode.respond_info('IMPORTANT: Restart Klipper to apply changes')
                self.gcode.respond_info('Run: FIRMWARE_RESTART')

        except json.JSONDecodeError as e:
            self.gcode.respond_info(f'Error: Invalid JSON in ORDER parameter: {e}')
        except Exception as e:
            self.gcode.respond_info(f'Error reordering devices: {e}')

    cmd_ACE_START_DRYING_help = 'Start dryer on a specific ACE device'

    def cmd_ACE_START_DRYING(self, gcmd):
        """Start dryer on a specific ACE device by device ID or gate number"""
        device_id = gcmd.get('DEVICE', None)
        gate = gcmd.get_int('GATE', None)
        temp = gcmd.get_int('TEMP', None)
        duration = gcmd.get_int('DURATION', 240)

        if temp is None:
            self.gcode.respond_info('Error: TEMP parameter required')
            self.gcode.respond_info('Usage: ACE_START_DRYING DEVICE=<device_id> TEMP=<temp> DURATION=<minutes>')
            self.gcode.respond_info('   or: ACE_START_DRYING GATE=<gate_num> TEMP=<temp> DURATION=<minutes>')
            return

        # Find target device
        target_device = None
        target_ace = None

        if device_id:
            # Find by device ID
            for dev in self.ace_devices:
                if dev.get('device_id') == device_id:
                    target_device = dev
                    target_ace = dev['instance']
                    break
            if not target_device:
                self.gcode.respond_info(f'Error: Device {device_id} not found')
                return
        elif gate is not None:
            # Find by gate number
            for dev in self.ace_devices:
                offset = dev['gate_offset']
                if offset <= gate < offset + 4:
                    target_device = dev
                    target_ace = dev['instance']
                    break
            if not target_device:
                self.gcode.respond_info(f'Error: Gate {gate} not found')
                return
        else:
            self.gcode.respond_info('Error: Either DEVICE or GATE parameter required')
            return

        # Validate temperature
        max_temp = target_ace.max_dryer_temperature if hasattr(target_ace, 'max_dryer_temperature') else 70
        if temp <= 0 or temp > max_temp:
            self.gcode.respond_info(f'Error: Temperature must be between 1 and {max_temp}°C')
            return

        # Validate duration
        if duration <= 0:
            self.gcode.respond_info('Error: Duration must be greater than 0 minutes')
            return

        # Call the ACE device's start drying method
        device_name = target_device.get('name', f"ACE Unit {target_device['gate_offset']//4 + 1}")

        # Create a pseudo gcmd for the ACE instance
        class PseudoGcmd:
            def __init__(self, temp, duration):
                self._temp = temp
                self._duration = duration

            def get_int(self, key, default=None):
                if key == 'TEMP':
                    return self._temp
                elif key == 'DURATION':
                    return self._duration
                return default

        pseudo_gcmd = PseudoGcmd(temp, duration)
        target_ace.cmd_ACE_START_DRYING(pseudo_gcmd)

        self.gcode.respond_info(f'Started dryer on {device_name} at {temp}°C for {duration} minutes')

    cmd_ACE_STOP_DRYING_help = 'Stop dryer on a specific ACE device'

    def cmd_ACE_STOP_DRYING(self, gcmd):
        """Stop dryer on a specific ACE device by device ID or gate number"""
        device_id = gcmd.get('DEVICE', None)
        gate = gcmd.get_int('GATE', None)

        # Find target device
        target_device = None
        target_ace = None

        if device_id:
            # Find by device ID
            for dev in self.ace_devices:
                if dev.get('device_id') == device_id:
                    target_device = dev
                    target_ace = dev['instance']
                    break
            if not target_device:
                self.gcode.respond_info(f'Error: Device {device_id} not found')
                return
        elif gate is not None:
            # Find by gate number
            for dev in self.ace_devices:
                offset = dev['gate_offset']
                if offset <= gate < offset + 4:
                    target_device = dev
                    target_ace = dev['instance']
                    break
            if not target_device:
                self.gcode.respond_info(f'Error: Gate {gate} not found')
                return
        else:
            self.gcode.respond_info('Error: Either DEVICE or GATE parameter required')
            self.gcode.respond_info('Usage: ACE_STOP_DRYING DEVICE=<device_id>')
            self.gcode.respond_info('   or: ACE_STOP_DRYING GATE=<gate_num>')
            return

        # Call the ACE device's stop drying method
        device_name = target_device.get('name', f"ACE Unit {target_device['gate_offset']//4 + 1}")

        # Create a pseudo gcmd
        class PseudoGcmd:
            pass

        pseudo_gcmd = PseudoGcmd()
        target_ace.cmd_ACE_STOP_DRYING(pseudo_gcmd)

        self.gcode.respond_info(f'Stopped dryer on {device_name}')

    cmd_ACE_GET_DRYER_STATUS_help = 'Show dryer status for all ACE devices'

    def cmd_ACE_GET_DRYER_STATUS(self, gcmd):
        """Show dryer status for all ACE devices"""
        self.gcode.respond_info("=" * 70)
        self.gcode.respond_info("ACE Dryer Status")
        self.gcode.respond_info("=" * 70)

        for dev in self.ace_devices:
            ace = dev['instance']
            status = ace.get_status()
            device_name = dev.get('name', f"ACE Unit {dev['gate_offset']//4 + 1}")
            device_id = dev.get('device_id', 'unknown')
            gate_offset = dev['gate_offset']
            gates_str = f"{gate_offset}-{gate_offset + 3}"

            dryer = status.get('dryer_status', {})
            dryer_status = dryer.get('status', 'unknown')
            temp = status.get('temp', 0)
            target_temp = dryer.get('target_temp', 0)
            duration = dryer.get('duration', 0)
            remain_time = dryer.get('remain_time', 0)

            self.gcode.respond_info(f"\n{device_name} ({device_id}) - Gates {gates_str}:")

            if dryer_status == 'running':
                self.gcode.respond_info(f"  Status:    🔥 Running")
                self.gcode.respond_info(f"  Current:   {temp}°C")
                self.gcode.respond_info(f"  Target:    {target_temp}°C")
                self.gcode.respond_info(f"  Duration:  {duration} minutes")
                self.gcode.respond_info(f"  Remaining: {remain_time} minutes")
            else:
                self.gcode.respond_info(f"  Status:    ⭘ Stopped")
                self.gcode.respond_info(f"  Current:   {temp}°C")

        self.gcode.respond_info("\n" + "=" * 70)
        self.gcode.respond_info("Commands:")
        self.gcode.respond_info("  ACE_START_DRYING DEVICE=<id> TEMP=<temp> DURATION=<min>")
        self.gcode.respond_info("  ACE_START_DRYING GATE=<num> TEMP=<temp> DURATION=<min>")
        self.gcode.respond_info("  ACE_STOP_DRYING DEVICE=<id>  or  ACE_STOP_DRYING GATE=<num>")
        self.gcode.respond_info("=" * 70)

def load_config(config):
    """Load single ACE or ACE Manager based on config parameters"""
    # Check if this is an ACE Manager config by looking for manager-specific params
    has_serial_ports = config.fileconfig.has_option(config.get_name(), 'serial_ports')
    has_ace_devices = config.fileconfig.has_option(config.get_name(), 'ace_devices')
    has_auto_detect = config.fileconfig.has_option(config.get_name(), 'auto_detect')

    # If any manager-specific param exists, load as AceManager
    if has_serial_ports or has_ace_devices or has_auto_detect:
        return AceManager(config)

    # Otherwise load as single BunnyAce
    return BunnyAce(config)

def load_config_prefix(config):
    """Load ACE instances with custom names like [ace ace1]"""
    return BunnyAce(config)

