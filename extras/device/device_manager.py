"""
Device manager for multiple ACE Pro devices.
Manages 0-4 ACE devices as a unified multi-gate system.
"""

import logging
import os
from typing import List, Dict, Optional, Tuple

from .ace_device import AceDevice
from .device_discovery import AceDeviceDiscovery
from .device_mapper import AceDeviceMapper
from ..protocol.constants import GATES_PER_ACE


class AceDeviceManager:
    """
    Manages pool of ACE Pro devices (0-4 physical units).

    Responsibilities:
    - Device enumeration (USB auto-detect or manual config)
    - Gate offset calculation (0-3, 4-7, 8-11, 12-15)
    - Routing global gates to specific devices
    - Hot-plug support and device persistence
    - Device lifecycle management

    Does NOT handle:
    - Tool change orchestration (belongs in AceController)
    - Sensor management (belongs in AceController)
    - G-code commands (belongs in AceController)
    """

    def __init__(self, printer, config, connect_retry_delay=1.0, connect_retry_max=10):
        """
        Initialize device manager.

        Args:
            printer: Klipper printer object
            config: Configuration object from Klipper
            connect_retry_delay: Retry delay for device connections
            connect_retry_max: Maximum connection retry attempts
        """
        self.printer = printer
        self.reactor = printer.get_reactor()
        self.config = config

        # Device tracking
        self.ace_devices = []  # List of device dicts: {'name', 'device_id', 'port', 'instance', 'gate_offset'}
        self.total_gates = 0
        self.device_ids = {}  # port -> device_id mapping

        # Configuration parameters
        self.baud = config.getint('baud', 115200)
        self.connect_retry_delay = connect_retry_delay
        self.connect_retry_max = connect_retry_max
        self.log_level = logging.INFO
        log_level_str = config.get('log_level', 'INFO').upper()
        if hasattr(logging, log_level_str):
            self.log_level = getattr(logging, log_level_str)

        # Check configuration method
        serial_ports_str = config.get('serial_ports', None)
        auto_detect = config.getboolean('auto_detect', False)

        if auto_detect:
            self._setup_auto_detect()
        elif serial_ports_str:
            self._setup_from_serial_ports(serial_ports_str)
        else:
            raise config.error("[ace] requires either 'auto_detect: true' or 'serial_ports: /dev/ttyACM0, ...'")

        # Calculate total gates
        self.total_gates = len(self.ace_devices) * GATES_PER_ACE

        logging.info(f"AceDeviceManager: Managing {len(self.ace_devices)} devices with {self.total_gates} total gates")

    def _setup_auto_detect(self):
        """Auto-detect ACE devices via USB enumeration"""
        logging.info("AceDeviceManager: Auto-detecting ACE devices...")

        # Discover devices
        discovered = AceDeviceDiscovery.find_ace_devices()

        if not discovered:
            logging.warning("AceDeviceManager: No ACE devices found")
            return

        # Probe each discovered device
        verified_devices = []
        for device_info in discovered:
            port = device_info.get('port')
            usb_location = device_info.get('location')

            if not port:
                continue

            # Probe device to get device_id
            probe_result = AceDeviceDiscovery.probe_ace_device(port, baud=self.baud, usb_location=usb_location)

            if probe_result:
                verified_devices.append({
                    'device_id': probe_result['device_id'],
                    'port': port,
                    'usb_location': usb_location or '',
                    'firmware': probe_result.get('firmware', 'unknown'),
                    'model': probe_result.get('model', 'ACE'),
                    'port_by_path': probe_result.get('port_by_path'),
                    'port_by_id': probe_result.get('port_by_id')
                })
                logging.info(f"AceDeviceManager: Found device {probe_result['device_id']} at {port}")

        # Sort by USB location for deterministic ordering
        verified_devices.sort(key=lambda d: d.get('usb_location', ''))

        # Create device instances
        for i, dev in enumerate(verified_devices):
            device_id = dev['device_id']
            port = dev['port']
            gate_offset = i * GATES_PER_ACE

            # Use stable by-path if available, otherwise fallback to regular port
            port_by_path = dev.get('port_by_path')
            port_by_id = dev.get('port_by_id')
            connection_port = port_by_path or port_by_id or port

            if port_by_path:
                logging.info(f"AceDeviceManager: Using by-path for {device_id}: {port_by_path}")
            elif port_by_id:
                logging.info(f"AceDeviceManager: Using by-id for {device_id}: {port_by_id}")
            else:
                logging.info(f"AceDeviceManager: Using regular port for {device_id}: {port}")

            # Create AceDevice instance
            ace_instance = AceDevice(
                port=connection_port,
                baud=self.baud,
                device_id=device_id,
                reactor=self.reactor,
                log_level=self.log_level,
                connect_retry_delay=self.connect_retry_delay,
                connect_retry_max=self.connect_retry_max
            )

            # Store device info
            self.ace_devices.append({
                'name': f"ACE_{i+1}",
                'device_id': device_id,
                'port': port,
                'instance': ace_instance,
                'gate_offset': gate_offset,
                'usb_location': dev.get('usb_location', ''),
                'port_by_path': dev.get('port_by_path'),
                'port_by_id': dev.get('port_by_id')
            })

            self.device_ids[port] = device_id

            logging.info(f"AceDeviceManager: Created {device_id} at gates {gate_offset}-{gate_offset+3}")

        # Initialize device mapper for persistence
        if verified_devices:
            config_dir = os.path.expanduser('~/printer_data/config')
            map_file = os.path.join(config_dir, 'ace_device_map.cfg')
            self.device_mapper = AceDeviceMapper(map_file)

            # Update device map
            for i, dev_info in enumerate(self.ace_devices):
                self.device_mapper.update_device(
                    dev_info['device_id'],
                    dev_info['port'],
                    dev_info.get('usb_location'),
                    dev_info['gate_offset'],
                    dev_info.get('port_by_path'),
                    dev_info.get('port_by_id')
                )

            self.device_mapper.save()
            logging.info(f"AceDeviceManager: Device map saved to {map_file}")

    def _setup_from_serial_ports(self, serial_ports_str: str):
        """Setup from comma-separated serial port list"""
        serial_ports = [p.strip() for p in serial_ports_str.split(',')]

        logging.info(f"AceDeviceManager: Setting up {len(serial_ports)} devices from serial_ports")

        for i, port in enumerate(serial_ports):
            device_id = f"port_{i}"  # Simple fallback ID
            gate_offset = i * GATES_PER_ACE

            # Create AceDevice instance
            ace_instance = AceDevice(
                port=port,
                baud=self.baud,
                device_id=device_id,
                reactor=self.reactor,
                log_level=self.log_level,
                connect_retry_delay=self.connect_retry_delay,
                connect_retry_max=self.connect_retry_max
            )

            # Store device info
            self.ace_devices.append({
                'name': f"ACE_{i+1}",
                'device_id': device_id,
                'port': port,
                'instance': ace_instance,
                'gate_offset': gate_offset
            })

            self.device_ids[port] = device_id

            logging.info(f"AceDeviceManager: Created device on {port} at gates {gate_offset}-{gate_offset+3}")

    def connect_all(self):
        """Connect to all ACE devices"""
        logging.info("AceDeviceManager: Connecting to all devices...")
        for device in self.ace_devices:
            ace_instance = device['instance']
            ace_instance.connect()

    def disconnect_all(self):
        """Disconnect from all ACE devices"""
        logging.info("AceDeviceManager: Disconnecting from all devices...")
        for device in self.ace_devices:
            ace_instance = device['instance']
            ace_instance.disconnect()

    def get_device_for_gate(self, global_gate: int) -> Tuple[AceDevice, int]:
        """
        Route global gate number to owning device and local gate.

        Args:
            global_gate: Global gate number (0-15 for 4 devices)

        Returns:
            Tuple of (AceDevice instance, local_gate)

        Raises:
            ValueError: If gate number is invalid
        """
        if global_gate < 0 or global_gate >= self.total_gates:
            raise ValueError(f"Invalid gate {global_gate} (valid: 0-{self.total_gates-1})")

        for device in self.ace_devices:
            offset = device['gate_offset']
            # Check if gate is in this device's range [offset, offset+4)
            if offset <= global_gate < offset + GATES_PER_ACE:
                local_gate = global_gate - offset
                return device['instance'], local_gate

        raise ValueError(f"Cannot route gate {global_gate}")

    def get_device_info_lightweight(self) -> List[Dict]:
        """
        Get lightweight device info (connection details only, no status).

        Returns:
            List of device info dictionaries without status data
        """
        return [
            {
                'name': dev['name'],
                'device_id': dev['device_id'],
                'port': dev['port'],
                'gate_offset': dev['gate_offset'],
                'gates': list(range(dev['gate_offset'], dev['gate_offset'] + GATES_PER_ACE)),
                'connected': dev['instance']._connected,
                'connection_status': 'connected' if dev['instance']._connected else 'disconnected',
                'model': dev['instance']._info.get('model', 'ACE Pro'),
                'firmware': dev['instance']._info.get('firmware', 'Unknown')
            }
            for dev in self.ace_devices
        ]

    def get_all_devices(self) -> List[Dict]:
        """
        Get list of all device info with full status.

        Returns:
            List of device info dictionaries including full status
        """
        return [
            {
                'name': dev['name'],
                'device_id': dev['device_id'],
                'port': dev['port'],
                'gate_offset': dev['gate_offset'],
                'gates': list(range(dev['gate_offset'], dev['gate_offset'] + GATES_PER_ACE)),
                'connected': dev['instance']._connected,
                'connection_status': 'connected' if dev['instance']._connected else 'disconnected',
                'model': dev['instance']._info.get('model', 'ACE Pro'),
                'firmware': dev['instance']._info.get('firmware', 'Unknown'),
                'health': {
                    'avg_response_time_ms': 0,  # TODO: Track actual response times
                    'error_count': 0,  # Removed _consecutive_write_errors tracking
                    'uptime': 0,  # TODO: Calculate from connection time
                    'temperature': dev['instance']._info.get('temp', 0),
                },
                'status': dev['instance'].get_status()
            }
            for dev in self.ace_devices
        ]

    def get_aggregated_status(self) -> Dict:
        """
        Get aggregated status from all devices.

        Returns:
            Combined status dictionary for Moonraker API
        """
        all_gate_status = []
        all_slots = []

        for device in self.ace_devices:
            ace = device['instance']
            status = ace.get_status()

            # Aggregate gate status
            all_gate_status.extend(status.get('active_gate', []))

            # Aggregate slots with adjusted indices
            offset = device['gate_offset']
            slots = status.get('slots', [])
            for slot in slots:
                adjusted_slot = slot.copy()
                adjusted_slot['index'] = slot['index'] + offset  # Adjust to global gate number
                all_slots.append(adjusted_slot)

        return {
            'total_gates': self.total_gates,
            'num_devices': len(self.ace_devices),
            'active_gate': all_gate_status,
            'slots': all_slots,
            'devices': self.get_all_devices()
        }

    def enumerate_devices(self) -> Dict:
        """
        Re-enumerate devices (for hot-plug support).

        Returns:
            Enumeration plan with changes detected
        """
        if not hasattr(self, 'device_mapper'):
            return {
                'current_devices': self.ace_devices,
                'discovered_devices': [],
                'added': [],
                'removed': [],
                'reordered': [],
                'unchanged': []
            }

        # Discover currently connected devices
        discovered = AceDeviceDiscovery.find_ace_devices()

        verified_devices = []
        for device_info in discovered:
            port = device_info.get('port')
            usb_location = device_info.get('location')

            if not port:
                continue

            # Check if port is already connected (skip probing to avoid conflicts)
            is_connected = any(d.get('port') == port for d in self.ace_devices)

            if is_connected:
                # Use existing device info
                existing_dev = next(d for d in self.ace_devices if d.get('port') == port)
                verified_devices.append({
                    'device_id': existing_dev['device_id'],
                    'port': port,
                    'usb_location': usb_location or existing_dev.get('usb_location', ''),
                    'existing': True
                })
            else:
                # Probe new device
                probe_result = AceDeviceDiscovery.probe_ace_device(port, baud=self.baud, usb_location=usb_location)
                if probe_result:
                    verified_devices.append({
                        'device_id': probe_result['device_id'],
                        'port': port,
                        'usb_location': usb_location or '',
                        'existing': False
                    })

        # Sort by USB location
        verified_devices.sort(key=lambda d: d.get('usb_location', ''))

        # Analyze changes
        current_device_ids = {d['device_id']: d for d in self.ace_devices}
        discovered_device_ids = {d['device_id']: d for d in verified_devices}

        added = []
        removed = []
        reordered = []
        unchanged = []

        # Calculate new gate offsets
        gate_offset_map = {}
        for i, dev in enumerate(verified_devices):
            gate_offset_map[dev['device_id']] = i * GATES_PER_ACE

        # Find added devices
        for device_id in discovered_device_ids:
            if device_id not in current_device_ids:
                added.append({
                    'device_id': device_id,
                    'gate_offset': gate_offset_map[device_id]
                })

        # Find removed devices
        for device_id in current_device_ids:
            if device_id not in discovered_device_ids:
                removed.append({
                    'device_id': device_id,
                    'gate_offset': current_device_ids[device_id]['gate_offset']
                })

        # Find reordered devices
        for device_id in discovered_device_ids:
            if device_id in current_device_ids:
                old_offset = current_device_ids[device_id]['gate_offset']
                new_offset = gate_offset_map[device_id]
                if old_offset != new_offset:
                    reordered.append({
                        'device_id': device_id,
                        'old_gate_offset': old_offset,
                        'new_gate_offset': new_offset
                    })
                else:
                    unchanged.append({
                        'device_id': device_id,
                        'gate_offset': new_offset
                    })

        return {
            'current_devices': self.ace_devices,
            'discovered_devices': verified_devices,
            'added': added,
            'removed': removed,
            'reordered': reordered,
            'unchanged': unchanged,
            'gate_offset_map': gate_offset_map
        }
