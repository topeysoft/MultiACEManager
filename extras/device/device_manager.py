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


def order_devices(devices, known_offsets=None, device_order=(), aliases=None):
    """
    Decide the gate order of discovered ACE devices.

    Priority:
      1. ``device_order`` from ``[ace]`` (device IDs or aliases), in the listed order
      2. devices seen before keep their relative order from the saved gate offsets
         (so re-cabling or adding a unit does not silently re-roll existing gates)
      3. never-seen devices follow, sorted by USB location

    Args:
        devices: list of dicts with at least ``device_id`` and ``usb_location``
        known_offsets: {device_id: last_gate_offset} for devices in the device map
        device_order: explicit order of device IDs / aliases (from config)
        aliases: {alias: device_id}

    Returns:
        A new list in gate order (offsets are assigned by position * GATES_PER_ACE).
    """
    known_offsets = known_offsets or {}
    aliases = aliases or {}
    explicit = [aliases.get(ref, ref) for ref in device_order]

    def rank(dev):
        device_id = dev['device_id']
        location = dev.get('usb_location') or ''
        if device_id in explicit:
            return (0, explicit.index(device_id), 0, location)
        if device_id in known_offsets:
            return (1, 0, known_offsets[device_id], location)
        return (2, 0, 0, location)

    return sorted(devices, key=rank)


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

        # Adaptive polling configuration
        from ..protocol.constants import DEFAULT_ADAPTIVE_POLLING, WRITER_POLL_INTERVAL
        self.adaptive_polling = config.getboolean('adaptive_polling', DEFAULT_ADAPTIVE_POLLING)
        self.fixed_poll_interval = config.getfloat('poll_interval', WRITER_POLL_INTERVAL)

        # Explicit gate order (device IDs or aliases); empty = remembered order, then USB location
        device_order_str = config.get('device_order', '')
        self.device_order = [s.strip() for s in device_order_str.split(',') if s.strip()]

        # Persistent device map (created up front so ordering can use remembered gate offsets)
        config_dir = os.path.expanduser('~/printer_data/config')
        self.device_mapper = AceDeviceMapper(os.path.join(config_dir, 'ace_device_map.cfg'))

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

        # Global I/O timer (single timer for all devices)
        self.global_io_timer = None
        self._last_global_interval = None

        logging.info(f"AceDeviceManager: Managing {len(self.ace_devices)} devices with {self.total_gates} total gates")
        logging.info(f"AceDeviceManager: Using single global timer for all devices")
        if self.adaptive_polling:
            logging.info(f"AceDeviceManager: Adaptive polling ENABLED (0.2s-30s based on activity)")
        else:
            logging.info(f"AceDeviceManager: Adaptive polling DISABLED (fixed {self.fixed_poll_interval}s interval)")

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
                    'port': probe_result['port'],  # This is now by-path
                    'port_tty': probe_result.get('port_tty'),  # ttyACM reference
                    'usb_location': usb_location or '',
                    'firmware': probe_result.get('firmware', 'unknown'),
                    'model': probe_result.get('model', 'ACE')
                })
                logging.info(f"AceDeviceManager: Found device {probe_result['device_id']}")
                logging.info(f"AceDeviceManager:   by-path: {probe_result['port']}")
                logging.info(f"AceDeviceManager:   tty ref: {probe_result.get('port_tty', 'N/A')}")

        # Order: config device_order, then remembered gate offsets, then USB location
        verified_devices = self.order_devices(verified_devices)

        # Create device instances
        for i, dev in enumerate(verified_devices):
            device_id = dev['device_id']
            port = dev['port']  # This is by-path
            gate_offset = i * GATES_PER_ACE

            # Create AceDevice instance (port is already by-path)
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
                'port': port,  # by-path
                'port_tty': dev.get('port_tty', ''),  # ttyACM reference
                'instance': ace_instance,
                'gate_offset': gate_offset,
                'usb_location': dev.get('usb_location', '')
            })

            self.device_ids[port] = device_id

            logging.info(f"AceDeviceManager: Created {device_id} at gates {gate_offset}-{gate_offset+3}")

        # Persist current ports and gate offsets
        if verified_devices:
            for i, dev_info in enumerate(self.ace_devices):
                self.device_mapper.update_device(
                    dev_info['device_id'],
                    dev_info['port'],  # by-path
                    dev_info.get('usb_location'),
                    dev_info['gate_offset'],
                    dev_info.get('port_tty')  # ttyACM reference
                )

            self.device_mapper.save()
            logging.info(f"AceDeviceManager: Device map saved to {self.device_mapper.config_path}")

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
        """Connect to all ACE devices and start global timer (non-blocking)"""
        logging.info("AceDeviceManager: Starting device connections (non-blocking)...")

        # Trigger connection attempts (async via timers)
        for device in self.ace_devices:
            ace_instance = device['instance']
            ace_instance.connect()

        # Start global I/O timer immediately (devices will connect asynchronously)
        if self.ace_devices and not self.global_io_timer:
            from ..protocol.constants import READY_WAIT_DELAY
            self.global_io_timer = self.reactor.register_timer(
                self._global_io_handler,
                self.reactor.monotonic() + READY_WAIT_DELAY
            )
            logging.info("AceDeviceManager: Started global I/O timer")
            logging.info("AceDeviceManager: Klipper startup continuing - devices will connect in background")

    def disconnect_all(self):
        """Disconnect from all ACE devices and stop global timer"""
        logging.info("AceDeviceManager: Disconnecting from all devices...")

        # Stop global timer
        if self.global_io_timer:
            try:
                self.reactor.unregister_timer(self.global_io_timer)
                self.global_io_timer = None
                logging.info("AceDeviceManager: Stopped global I/O timer")
            except Exception as e:
                logging.error(f"AceDeviceManager: Error stopping global timer: {e}")

        # Disconnect all devices
        for device in self.ace_devices:
            ace_instance = device['instance']
            ace_instance.disconnect()

    def order_devices(self, devices):
        """Apply the ordering rules (see module-level order_devices) using the device map."""
        known = {did: info.get('last_gate_offset', 0)
                 for did, info in self.device_mapper.get_all_devices().items()}
        return order_devices(devices, known, self.device_order, self.device_mapper.get_all_aliases())

    def resolve_device_ref(self, ref):
        """
        Resolve a user-supplied device reference to a connected device entry.
        Accepts the display name (ACE_1, ACE_2...), a 1-based index, a device_id, or an alias.
        """
        ref = str(ref).strip()
        for dev in self.ace_devices:
            if ref.upper() == dev['name'].upper():
                return dev
        if ref.isdigit():
            idx = int(ref) - 1
            if 0 <= idx < len(self.ace_devices):
                return self.ace_devices[idx]
        device_id = self.device_mapper.resolve_device_id(ref) or ref
        for dev in self.ace_devices:
            if dev['device_id'] == device_id:
                return dev
        return None

    def set_device_order(self, refs):
        """
        Re-assign gate ranges so the referenced devices come first, in the given order.
        Devices not listed keep their relative order after the listed ones.
        The new offsets are persisted in the device map and used at the next startup.

        Returns:
            list of (name, device_id, old_offset, new_offset)
        """
        ordered = []
        for ref in refs:
            dev = self.resolve_device_ref(ref)
            if dev is None:
                raise ValueError(f"Unknown device '{ref}' (use ACE_LIST_DEVICES names, device IDs or aliases)")
            if dev in ordered:
                raise ValueError(f"Device '{ref}' listed twice")
            ordered.append(dev)
        ordered += [dev for dev in self.ace_devices if dev not in ordered]

        changes = []
        for i, dev in enumerate(ordered):
            new_offset = i * GATES_PER_ACE
            changes.append((f"ACE_{i+1}", dev['device_id'], dev['gate_offset'], new_offset))
            dev['gate_offset'] = new_offset
            dev['name'] = f"ACE_{i+1}"
            self.device_mapper.update_device(dev['device_id'], dev['port'], dev.get('usb_location'),
                                             new_offset, dev.get('port_tty'))
        self.ace_devices = ordered
        self.device_mapper.save()
        logging.info(f"AceDeviceManager: Device order set to {[d['device_id'] for d in ordered]}")
        return changes

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

    def get_gate_offset_for_device(self, device_instance: AceDevice) -> int:
        """
        Get the global gate offset for a specific device instance.

        Args:
            device_instance: The AceDevice instance

        Returns:
            The gate offset for this device (0, 4, 8, or 12)

        Raises:
            ValueError: If device not found
        """
        for device in self.ace_devices:
            if device['instance'] == device_instance:
                return device['gate_offset']

        raise ValueError(f"Device {device_instance.device_id} not found in manager")

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
                'alias': self.device_mapper.get_alias(dev['device_id']),
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
                'alias': self.device_mapper.get_alias(dev['device_id']),
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

        # Same ordering rules as startup
        verified_devices = self.order_devices(verified_devices)

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

    def _global_io_handler(self, eventtime):
        """
        Single global I/O handler for all ACE devices.
        Polls all devices sequentially, preventing timer conflicts.
        """
        try:
            # Poll each device (sequential, but very fast ~1ms each)
            connected_count = 0
            for device_info in self.ace_devices:
                device = device_info['instance']
                if device._connected:
                    connected_count += 1
                    device.process_io(eventtime)

            # Log connection status periodically
            if not hasattr(self, '_last_status_log_time'):
                self._last_status_log_time = 0

            if eventtime - self._last_status_log_time > 30.0:  # Every 30s
                logging.info(f"AceDeviceManager: {connected_count}/{len(self.ace_devices)} devices connected")
                for device_info in self.ace_devices:
                    device = device_info['instance']
                    status = "CONNECTED" if device._connected else "DISCONNECTED"
                    device_status = device._info.get('status', 'unknown')
                    logging.info(f"  {device.device_id}: {status}, status={device_status}")
                self._last_status_log_time = eventtime

            # Calculate adaptive interval based on ANY device activity
            interval = self._get_global_adaptive_interval()

            # Log interval changes
            if interval != self._last_global_interval:
                if interval == 30.0:
                    logging.info(f"AceDeviceManager: All devices IDLE (30s heartbeat)")
                elif interval <= 0.5:
                    logging.debug(f"AceDeviceManager: Active devices detected ({interval}s polling)")
                self._last_global_interval = interval

            return eventtime + interval

        except Exception as e:
            logging.error(f"AceDeviceManager: Global I/O handler error: {e}")
            import traceback
            traceback.print_exc()
            return eventtime + 5.0  # Failsafe

    def _get_global_adaptive_interval(self):
        """
        Get polling interval - either adaptive or fixed based on configuration.
        Returns the fastest interval needed by any device (if adaptive enabled).
        """
        try:
            # If adaptive polling disabled, return fixed interval
            if not self.adaptive_polling:
                return self.fixed_poll_interval

            # Adaptive polling: find fastest interval needed
            fastest_interval = 30.0  # Start with slowest (idle)

            for device_info in self.ace_devices:
                device = device_info['instance']
                if device._connected:
                    # Get device's desired interval
                    device_interval = device._get_adaptive_poll_interval()
                    fastest_interval = min(fastest_interval, device_interval)

            # Enforce minimum to prevent timer conflicts
            return max(0.2, fastest_interval)

        except Exception as e:
            logging.warning(f"AceDeviceManager: Error in polling interval calculation: {e}")
            return 5.0  # Failsafe

    def wait_all_devices_ready(self, timeout: float = 30.0):
        """
        Wait for all ACE devices and all their gates to become ready (idle).

        This is critical for preventing race conditions during tool changes
        where one device might start feeding while another is still retracting.

        Waits for both:
        1. Device-level status to be 'ready'
        2. All gate-level statuses to be 'ready' or 'empty'

        Args:
            timeout: Maximum time to wait in seconds (default: 30s)

        Raises:
            Exception: If any device or gate doesn't become ready within timeout
        """
        start_time = self.reactor.monotonic()

        for device_info in self.ace_devices:
            device = device_info['instance']
            device_id = device.device_id

            # Check remaining timeout
            elapsed = self.reactor.monotonic() - start_time
            remaining_timeout = timeout - elapsed

            if remaining_timeout <= 0:
                raise Exception(f"Timeout waiting for all devices to become ready")

            # Wait for device-level status
            logging.debug(f"AceDeviceManager: Waiting for device {device_id} to be ready...")
            device.wait_ready(timeout=remaining_timeout)

            # Wait for all gates on this device to be ready
            for local_gate in range(device.num_gates):
                elapsed = self.reactor.monotonic() - start_time
                remaining_timeout = timeout - elapsed

                if remaining_timeout <= 0:
                    raise Exception(f"Timeout waiting for all gates to become ready")

                logging.debug(f"AceDeviceManager: Waiting for device {device_id} gate {local_gate} to be ready...")
                device.wait_gate_ready(local_gate, timeout=remaining_timeout)

        logging.debug(f"AceDeviceManager: All {len(self.ace_devices)} devices and {self.total_gates} gates are ready")

    @property
    def devices(self):
        """
        Get list of all AceDevice instances.

        Returns:
            List of AceDevice instances
        """
        return [dev['instance'] for dev in self.ace_devices]
