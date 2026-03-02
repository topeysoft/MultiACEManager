#!/usr/bin/env python3
"""
ACE Pro Multi-Port Probe
Auto-detects ACE Pro devices and generates Klipper configuration
"""

import serial
import struct
import json
import time
import sys
import argparse
import glob
from pathlib import Path

def calc_crc(buffer):
    """Calculate CRC for ACE protocol"""
    _crc = 0xffff
    for byte in buffer:
        data = byte
        data ^= _crc & 0xff
        data ^= (data & 0x0f) << 4
        _crc = ((data << 8) | (_crc >> 8)) ^ (data >> 4) ^ (data << 3)
    return _crc

def send_ace_request(serial_port, method, params=None):
    """Send a request using ACE protocol"""
    request = {
        "id": 1,
        "method": method
    }
    if params:
        request["params"] = params

    payload = json.dumps(request).encode('utf-8')

    # Build packet: [0xFF 0xAA] [length] [payload] [crc] [0xFE]
    data = bytes([0xFF, 0xAA])
    data += struct.pack('@H', len(payload))
    data += payload
    data += struct.pack('@H', calc_crc(payload))
    data += bytes([0xFE])

    serial_port.write(data)
    serial_port.flush()

def read_ace_response(serial_port, timeout=2.0):
    """Read and parse ACE protocol response"""
    start_time = time.time()
    buffer = bytearray()

    while (time.time() - start_time) < timeout:
        if serial_port.in_waiting:
            buffer += serial_port.read(serial_port.in_waiting)

            # Look for terminator
            term_idx = buffer.find(b'\xfe')
            if term_idx >= 0:
                # Check for valid header
                if len(buffer) >= 7 and buffer[0:2] == bytes([0xFF, 0xAA]):
                    payload_len = struct.unpack('<H', buffer[2:4])[0]
                    payload = buffer[4:4 + payload_len]

                    try:
                        response = json.loads(payload.decode('utf-8'))
                        return response
                    except:
                        return {"error": "Invalid JSON"}
                else:
                    return {"error": "Invalid header"}
        time.sleep(0.05)

    return {"error": "Timeout"}

def probe_ace_device(port_path, verbose=False):
    """
    Probe a port to see if it's an ACE device
    Returns: dict with device info or None if not an ACE
    """
    try:
        ser = serial.Serial(
            port=port_path,
            baudrate=115200,
            timeout=0,
            write_timeout=0
        )

        # Try get_info first
        send_ace_request(ser, "get_info")
        info_response = read_ace_response(ser, timeout=1.0)

        if "error" not in info_response and "result" in info_response:
            # This is an ACE device!
            device_info = {
                'port': port_path,
                'model': info_response['result'].get('model', 'Unknown'),
                'firmware': info_response['result'].get('firmware', 'Unknown'),
                'slots': info_response['result'].get('slots', 4),
                'is_ace': True
            }

            # Get status to confirm slot count
            send_ace_request(ser, "get_status")
            status_response = read_ace_response(ser, timeout=1.0)

            if "error" not in status_response and "result" in status_response:
                if "slots" in status_response["result"]:
                    device_info['slots'] = len(status_response["result"]["slots"])

            ser.close()
            return device_info

        ser.close()
        return None

    except (serial.SerialException, OSError):
        return None
    except Exception as e:
        if verbose:
            print(f"  Error probing {port_path}: {e}")
        return None

def find_all_ace_devices(verbose=False):
    """
    Scan all /dev/ttyACM* ports and find ACE devices
    Returns: list of ACE device info dicts
    """
    ace_devices = []
    ttyacm_ports = sorted(glob.glob('/dev/ttyACM*'))

    if verbose:
        print(f"Scanning {len(ttyacm_ports)} serial ports...")

    for port in ttyacm_ports:
        if verbose:
            print(f"  Checking {port}...", end=' ')

        device_info = probe_ace_device(port, verbose=verbose)

        if device_info:
            ace_devices.append(device_info)
            if verbose:
                print(f"✓ ACE Pro found (FW: {device_info['firmware']})")
        else:
            if verbose:
                print("✗ Not an ACE device")

    return ace_devices

def generate_config(ace_devices):
    """Generate Klipper configuration for detected ACE devices"""
    if not ace_devices:
        return "# No ACE devices detected"

    total_gates = sum(d['slots'] for d in ace_devices)
    serial_list = ', '.join(d['port'] for d in ace_devices)

    config = []
    config.append("# ACE Pro Configuration")
    config.append(f"# Auto-generated for {len(ace_devices)} ACE device(s) - {total_gates} total gates")
    config.append("#")

    for i, device in enumerate(ace_devices):
        offset = i * 4
        config.append(f"# {device['port']}: ACE {i+1} - Gates {offset}-{offset+3} (FW: {device['firmware']})")

    config.append("")

    config.append("[ace]")
    config.append(f"serial_ports: {serial_list}")
    config.append("")
    config.append("# Shared configuration for all ACE devices")
    config.append("extruder_sensor_pin: YOUR_EXTRUDER_SENSOR_PIN  # Update this!")
    config.append("toolhead_sensor_pin: YOUR_TOOLHEAD_SENSOR_PIN  # Update this! (optional)")
    config.append("feed_speed: 80")
    config.append("retract_speed: 80")
    config.append("toolchange_retract_length: 170  # Distance from splitter to extruder")
    config.append("toolchange_feed_length: 800")
    config.append("toolhead_sensor_to_nozzle: 40")
    config.append("poop_macros: _POOP")
    config.append("cut_macros: _CUT_TIP")
    config.append("max_dryer_temperature: 70")

    # Add T macros
    config.append("")
    config.append("# Tool change macros")
    for i in range(total_gates):
        config.append(f"[gcode_macro T{i}]")
        config.append("gcode:")
        config.append(f"    ACE_CHANGE_TOOL TOOL={i}")
        config.append("")

    return '\n'.join(config)

def print_summary(ace_devices):
    """Print a summary of detected devices"""
    if not ace_devices:
        print("\n❌ No ACE Pro devices detected")
        print("\nPossible reasons:")
        print("  - ACE devices not connected")
        print("  - Klipper is running (stop it first: sudo systemctl stop klipper)")
        print("  - Wrong USB ports")
        return

    total_gates = sum(d['slots'] for d in ace_devices)

    print(f"\n✅ Found {len(ace_devices)} ACE Pro device(s)")
    print(f"Total gates available: {total_gates}\n")

    for i, device in enumerate(ace_devices):
        offset = i * 4
        print(f"  [{i+1}] {device['port']}")
        print(f"      Model: {device['model']}")
        print(f"      Firmware: {device['firmware']}")
        print(f"      Slots: {device['slots']}")
        print(f"      Gates: {offset}-{offset+3} (T{offset}-T{offset+3})")
        print()

def main():
    parser = argparse.ArgumentParser(
        description='ACE Pro Auto-Detection and Configuration Generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick scan (summary only)
  python3 probe_ace_ports.py -q

  # Verbose scan
  python3 probe_ace_ports.py -v

  # Generate config
  python3 probe_ace_ports.py --generate-config

  # Scan specific ports
  python3 probe_ace_ports.py /dev/ttyACM0 /dev/ttyACM1
        """
    )

    parser.add_argument('ports', nargs='*', help='Specific ports to probe (default: auto-scan)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Quiet mode (summary only)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--generate-config', action='store_true', help='Generate Klipper config')


    args = parser.parse_args()

    # Set verbosity
    verbose = args.verbose and not args.quiet

    if not args.quiet:
        print("=" * 70)
        print("ACE Pro Auto-Detection Tool")
        print("=" * 70)

    # Find ACE devices
    if args.ports:
        # Probe specific ports
        ace_devices = []
        for port in args.ports:
            if verbose:
                print(f"\nProbing {port}...")
            device_info = probe_ace_device(port, verbose=verbose)
            if device_info:
                ace_devices.append(device_info)
    else:
        # Auto-scan all ports
        if verbose:
            print()
        ace_devices = find_all_ace_devices(verbose=verbose)

    # Output results
    if not args.quiet:
        print_summary(ace_devices)

    # Generate config if requested
    if args.generate_config:
        if ace_devices:
            print("\n" + "=" * 70)
            print("GENERATED CONFIGURATION")
            print("=" * 70 + "\n")
            print(generate_config(ace_devices))
            print("\n" + "=" * 70)
            print("Copy the above configuration to your printer.cfg")
            print("Don't forget to update the sensor pins!")
            print("=" * 70)
        else:
            print("\n❌ Cannot generate config - no ACE devices found")
    elif args.quiet:
        # Quiet mode - just output serial port list
        if ace_devices:
            print(', '.join(d['port'] for d in ace_devices))
        else:
            sys.exit(1)

if __name__ == "__main__":
    main()
