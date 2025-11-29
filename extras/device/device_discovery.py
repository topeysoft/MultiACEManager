"""
ACE device USB auto-discovery and enumeration.
Handles detection, identification, and probing of ACE devices on USB ports.
"""

import serial
import serial.tools.list_ports
import json
import struct
import time
import logging
import hashlib
import re

from ..protocol.constants import (
    PROTOCOL_HEAD_BYTES,
    PROTOCOL_TAIL_BYTE,
    PROTOCOL_MIN_PACKET_SIZE,
    CRC_INIT_VALUE
)
from ..protocol.packet import AcePacket, calc_crc


class AceDeviceDiscovery:
    """Handles auto-discovery and enumeration of ACE devices"""

    ACE_VID = 0x28E9  # GDMicroelectronics vendor ID
    ACE_PID = 0x018A  # ACE product ID
    ACE_MANUFACTURER = "GDMicroelectronics"
    ACE_PRODUCT_NAME = "ACE"

    @staticmethod
    def sanitize_device_id(device_id):
        """
        Sanitize device_id to create a valid Python identifier for use in save_variables.

        Replaces all non-alphanumeric characters (except underscores) with underscores.
        This ensures device IDs can be safely used as Python variable names.

        Args:
            device_id: Raw device identifier (e.g., 'hub_1_port_1.3.3.3:1.0')

        Returns:
            Sanitized device ID safe for use as Python variable name
            (e.g., 'hub_1_port_1_3_3_3_1_0')

        Examples:
            >>> sanitize_device_id('hub_1_port_1.3.3.3:1.0')
            'hub_1_port_1_3_3_3_1_0'
            >>> sanitize_device_id('mac:AA:BB:CC:DD:EE:FF')
            'mac_AA_BB_CC_DD_EE_FF'
        """
        return re.sub(r'[^a-zA-Z0-9_]', '_', device_id)

    @staticmethod
    def find_ace_devices():
        """
        Scan all USB serial ports and identify ACE devices
        Returns: List of dicts with port info and device details
        """
        ace_devices = []
        ports = serial.tools.list_ports.comports()

        logging.info(f"ACE Device Discovery: Scanning {len(ports)} USB serial ports...")

        for port in ports:
            # Log all ports for debugging
            logging.info(f"  Port: {port.device}")
            logging.info(f"    VID:PID = 0x{port.vid:04X}:0x{port.pid:04X}" if port.vid and port.pid else f"    VID:PID = None")
            logging.info(f"    Manufacturer: {port.manufacturer}")
            logging.info(f"    Product: {port.product}")
            logging.info(f"    Serial: {port.serial_number}")
            logging.info(f"    Location: {port.location}")

            # Method 1: VID/PID matching (most reliable)
            if port.vid == AceDeviceDiscovery.ACE_VID:
                logging.info(f"    ✓ Matched by VID (0x{AceDeviceDiscovery.ACE_VID:04X})")
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
                logging.info(f"    ✓ Matched by manufacturer/product string")
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
            else:
                logging.info(f"    ✗ No match (looking for VID=0x{AceDeviceDiscovery.ACE_VID:04X} or mfr='{AceDeviceDiscovery.ACE_MANUFACTURER}' or product='{AceDeviceDiscovery.ACE_PRODUCT_NAME}')")

        # Sort by USB location for deterministic ordering
        ace_devices.sort(key=lambda x: x.get('location', '') or '')

        logging.info(f"ACE Device Discovery: Found {len(ace_devices)} ACE devices")
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
        logging.info(f"ACE Probe: Attempting to probe {port} at {baud} baud...")
        try:
            ser = serial.Serial(
                port=port,
                baudrate=baud,
                timeout=timeout,
                write_timeout=timeout
            )
            logging.info(f"ACE Probe: Serial port {port} opened successfully")

            # Send get_info request using ACE protocol
            request = {"id": 1, "method": "get_info"}

            # Use AcePacket encoder
            packet_data = AcePacket.encode(request)

            logging.info(f"ACE Probe: Sending get_info command to {port}...")
            ser.write(packet_data)
            time.sleep(0.5)  # Wait for response

            # Try to read response
            bytes_waiting = ser.in_waiting
            logging.info(f"ACE Probe: {bytes_waiting} bytes waiting in buffer")

            if bytes_waiting > 0:
                response_data = ser.read(bytes_waiting)
                logging.info(f"ACE Probe: Received {len(response_data)} bytes: {response_data.hex()[:100]}...")

                # Use AcePacket decoder
                response_json, error = AcePacket.decode(response_data)

                if error:
                    logging.warning(f"ACE Probe: {error}")
                elif response_json and 'result' in response_json:
                    result = response_json['result']
                    # Add USB location to result for device_id generation
                    if usb_location:
                        result['usb_location'] = usb_location
                    device_id = AceDeviceDiscovery._generate_device_id(result)

                    logging.info(f"ACE Probe: ✓ Successfully verified ACE device '{device_id}' at {port}")
                    ser.close()
                    return {
                        'device_id': device_id,
                        'model': result.get('model', 'Unknown'),
                        'firmware': result.get('firmware', 'Unknown'),
                        'serial_number': result.get('serial_number', None),
                        'mac_address': result.get('mac_address', None),
                        'num_gates': 4  # Default, can be detected from slots
                    }
                else:
                    logging.warning(f"ACE Probe: Response missing 'result' field: {response_json}")
            else:
                logging.warning(f"ACE Probe: No response received from {port} (timeout after {timeout}s)")

            ser.close()
            logging.info(f"ACE Probe: ✗ Device at {port} did not respond as expected ACE device")
            return None

        except serial.SerialException as e:
            logging.warning(f"ACE Probe: Serial error on {port}: {e}")
            return None
        except Exception as e:
            logging.error(f"ACE Probe: Unexpected error probing {port}: {e}")
            import traceback
            logging.error(traceback.format_exc())
            return None

    @staticmethod
    def _generate_device_id(device_info):
        """
        Generate device ID based on USB port location.
        This ensures the same physical USB port always maps to the same device ID,
        making gate assignments stable and predictable across reboots.

        Format: hub_1_port_3 (readable) from USB location like "1-1.3"
        """
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
                port_path = parts[1]
                device_id = f"hub_{parts[0]}_port_{port_path}"
            else:
                # Fallback for simple format
                device_id = f"usb_{usb_loc}"

            # Sanitize to ensure valid Python identifier
            return AceDeviceDiscovery.sanitize_device_id(device_id)

        # Fallback: MAC address (if firmware provides it)
        if 'mac_address' in device_info and device_info['mac_address']:
            mac = device_info['mac_address']
            logging.info(f"ACE: Using MAC address for device_id (USB location not available)")
            return AceDeviceDiscovery.sanitize_device_id(f"mac_{mac}")

        # Fallback: Serial number (if firmware provides it)
        if 'serial_number' in device_info and device_info['serial_number']:
            sn = device_info['serial_number']
            logging.info(f"ACE: Using serial number for device_id (USB location not available)")
            return AceDeviceDiscovery.sanitize_device_id(f"sn_{sn}")

        # Last resort: Hash of firmware + model (NOT recommended - not unique across identical devices)
        unique_str = f"{device_info.get('model', '')}_{device_info.get('firmware', '')}"
        hash_val = hashlib.md5(unique_str.encode()).hexdigest()[:8]
        logging.warning(f"ACE: Using firmware hash for device_id (not unique!). Consider using USB hub for stable port locations.")
        return f"fw_{hash_val}"
