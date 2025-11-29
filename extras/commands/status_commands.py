"""
Status and diagnostic commands for ACE Pro system.

Commands:
- ACE_GET_STATUS - Display system status
- ACE_SCAN_DEVICES - Scan for ACE devices
- ACE_LIST_DEVICES - List connected devices
- ACE_SHOW_USB_INFO - Show USB topology
"""

import logging
from ..device import AceDeviceDiscovery


class StatusCommands:
    """
    Status and diagnostic commands.

    This class contains all G-code commands related to querying
    the ACE system status and diagnostics.
    """

    def __init__(self, controller):
        """
        Initialize status commands.

        Args:
            controller: AceController instance
        """
        self.controller = controller
        self.gcode = controller.gcode
        self.device_manager = controller.device_manager
        self.save_variables = controller.save_variables

    def register(self):
        """Register all status commands"""
        self.gcode.register_command(
            'ACE_GET_STATUS', self.cmd_ACE_GET_STATUS,
            desc='Get ACE system status')

        self.gcode.register_command(
            'ACE_SCAN_DEVICES', self.cmd_ACE_SCAN_DEVICES,
            desc='Scan for ACE devices on USB')

        self.gcode.register_command(
            'ACE_LIST_DEVICES', self.cmd_ACE_LIST_DEVICES,
            desc='List all connected ACE devices')

        self.gcode.register_command(
            'ACE_SHOW_USB_INFO', self.cmd_ACE_SHOW_USB_INFO,
            desc='Show USB topology and device mapping')

        logging.info("StatusCommands: Registered 4 diagnostic commands")

    def cmd_ACE_GET_STATUS(self, gcmd):
        """
        ACE_GET_STATUS [DEVICE=<n>] [VERBOSE=<0|1>]

        Display ACE system status.

        Options:
            DEVICE - Show details for specific device only (0-3)
            VERBOSE - Show detailed gate information (default: 0)

        Examples:
            ACE_GET_STATUS              # Show summary
            ACE_GET_STATUS VERBOSE=1    # Show detailed info
            ACE_GET_STATUS DEVICE=0     # Show device 0 only
        """
        device_filter = gcmd.get_int('DEVICE', None)
        verbose = gcmd.get_int('VERBOSE', 0)

        status = self.device_manager.get_aggregated_status()

        # Header
        self.gcode.respond_info('=== ACE System Status ===')
        self.gcode.respond_info(f'Total Gates: {status["total_gates"]}')
        self.gcode.respond_info(f'Devices: {status["num_devices"]}')
        self.gcode.respond_info(f'Current Tool: {self.controller.current_tool}')

        # Endless spool status
        endless_spool = self.save_variables.allVariables.get('ace_endless_spool', False)
        endless_status = 'Enabled' if endless_spool else 'Disabled'
        self.gcode.respond_info(f'Endless Spool: {endless_status}')

        # Device information
        self.gcode.respond_info('\n=== Devices ===')
        for i, dev in enumerate(status['devices']):
            # Skip if filtering by device
            if device_filter is not None and i != device_filter:
                continue

            conn_status = '✓' if dev['connected'] else '✗'
            gates_str = f"{dev['gate_offset']}-{dev['gate_offset']+3}"
            self.gcode.respond_info(f"{conn_status} {dev['name']}: Gates {gates_str}")

            # Show detailed info if verbose or filtering
            if verbose or device_filter is not None:
                self._show_device_details(dev)

        # Gate configuration (if verbose)
        if verbose:
            self._show_gate_configuration(status["total_gates"])

    def _show_device_details(self, device_info):
        """
        Show detailed information for a device.

        Args:
            device_info: Device information dictionary
        """
        self.gcode.respond_info(f'    Port: {device_info.get("port", "N/A")}')
        self.gcode.respond_info(f'    ID: {device_info["name"]}')
        self.gcode.respond_info(f'    Gates: {device_info["gate_offset"]}-{device_info["gate_offset"]+3}')

        # Gate states if available
        if 'active_gate' in device_info and device_info['active_gate']:
            self.gcode.respond_info('    Gate States:')
            gate_offset = device_info['gate_offset']
            for local_gate, state in enumerate(device_info['active_gate'][:4]):
                global_gate = gate_offset + local_gate
                self.gcode.respond_info(f'      Gate {global_gate}: {state}')

    def _apply_discovered_devices(self, discovered_devices):
        """
        Apply discovered devices to the device manager.

        Args:
            discovered_devices: List of discovered device dictionaries
        """
        from ..protocol.constants import GATES_PER_ACE

        # Disconnect all current devices
        self.device_manager.disconnect_all()

        # Clear current device list
        self.device_manager.ace_devices.clear()
        self.device_manager.device_ids.clear()

        # Probe and verify each discovered device
        verified_devices = []
        for device_info in discovered_devices:
            port = device_info.get('port')
            usb_location = device_info.get('location')

            if not port:
                continue

            # Probe device to get full info
            probe_result = AceDeviceDiscovery.probe_ace_device(
                port,
                baud=self.device_manager.baud,
                usb_location=usb_location
            )

            if probe_result:
                verified_devices.append({
                    'device_id': probe_result['device_id'],
                    'port': port,
                    'usb_location': usb_location or '',
                    'firmware': probe_result.get('firmware', 'unknown'),
                    'model': probe_result.get('model', 'ACE')
                })
                logging.info(f"StatusCommands: Verified device {probe_result['device_id']} at {port}")

        # Sort by USB location for deterministic ordering
        verified_devices.sort(key=lambda d: d.get('usb_location', ''))

        # Create device instances
        from ..device.ace_device import AceDevice
        for i, dev in enumerate(verified_devices):
            device_id = dev['device_id']
            port = dev['port']
            gate_offset = i * GATES_PER_ACE

            # Create AceDevice instance
            ace_instance = AceDevice(
                port=port,
                baud=self.device_manager.baud,
                device_id=device_id,
                reactor=self.device_manager.reactor,
                log_level=self.device_manager.log_level,
                connect_retry_delay=self.device_manager.connect_retry_delay,
                connect_retry_max=self.device_manager.connect_retry_max
            )

            # Store device info
            self.device_manager.ace_devices.append({
                'name': f"ACE_{i+1}",
                'device_id': device_id,
                'port': port,
                'instance': ace_instance,
                'gate_offset': gate_offset,
                'usb_location': dev.get('usb_location', '')
            })

            self.device_manager.device_ids[port] = device_id

            logging.info(f"StatusCommands: Created {device_id} at gates {gate_offset}-{gate_offset+3}")

        # Update total gates
        self.device_manager.total_gates = len(self.device_manager.ace_devices) * GATES_PER_ACE

        # Save device mapping if device mapper exists
        if hasattr(self.device_manager, 'device_mapper'):
            for dev_info in self.device_manager.ace_devices:
                self.device_manager.device_mapper.update_device(
                    dev_info['device_id'],
                    dev_info['port'],
                    dev_info.get('usb_location'),
                    dev_info['gate_offset']
                )
            self.device_manager.device_mapper.save()

        # Reconnect all devices
        self.device_manager.connect_all()

        logging.info(f"StatusCommands: Applied {len(verified_devices)} devices with {self.device_manager.total_gates} total gates")

    def _show_gate_configuration(self, total_gates):
        """
        Show gate configuration (colors, materials, temps).

        Args:
            total_gates: Total number of gates in system
        """
        gate_colors = self.save_variables.allVariables.get(
            'ace_gate_color',
            ['FFFFFF'] * total_gates
        )
        gate_materials = self.save_variables.allVariables.get(
            'ace_gate_type',
            [''] * total_gates
        )
        gate_temps = self.save_variables.allVariables.get(
            'ace_gate_temp',
            [230] * total_gates
        )

        # Ensure arrays match total gates
        while len(gate_colors) < total_gates:
            gate_colors.append('FFFFFF')
        while len(gate_materials) < total_gates:
            gate_materials.append('')
        while len(gate_temps) < total_gates:
            gate_temps.append(230)

        self.gcode.respond_info('\n=== Gate Configuration ===')
        for i in range(total_gates):
            color = gate_colors[i]
            material = gate_materials[i] if gate_materials[i] else 'Unknown'
            temp = gate_temps[i]

            # Format output
            gate_str = f'Gate {i:2d}'
            color_str = f'#{color}'
            material_str = f'{material:8s}'
            temp_str = f'{temp}°C'

            # Add marker if this is the current tool
            current = ' ← Current' if i == self.controller.current_tool else ''

            self.gcode.respond_info(f'  {gate_str}: {color_str} {material_str} {temp_str}{current}')

    def cmd_ACE_SCAN_DEVICES(self, gcmd):
        """
        ACE_SCAN_DEVICES [APPLY=<0|1>]

        Scan USB ports for ACE devices and display results.

        Options:
            APPLY - If set to 1, apply discovered devices and restart connections (default: 0)

        WARNING: This command performs blocking USB I/O and may take several seconds.
        Using APPLY=1 will disconnect and reconnect all devices.
        """
        apply_changes = gcmd.get_int('APPLY', 0)

        self.gcode.respond_info('Scanning for ACE devices...')
        self.gcode.respond_info('(This may take a few seconds...)')

        try:
            discovered = AceDeviceDiscovery.find_ace_devices()

            if not discovered:
                self.gcode.respond_info('No ACE devices found')
                return

            self.gcode.respond_info(f'Found {len(discovered)} ACE device(s):')
            for i, dev in enumerate(discovered):
                self.gcode.respond_info(f'\nDevice {i+1}:')
                self.gcode.respond_info(f'  Port: {dev["port"]}')
                self.gcode.respond_info(f'  Device ID: {dev["device_id"]}')
                if dev.get('usb_location'):
                    self.gcode.respond_info(f'  USB Location: {dev["usb_location"]}')
                if dev.get('serial_number'):
                    self.gcode.respond_info(f'  Serial: {dev["serial_number"]}')

            # Apply changes if requested
            if apply_changes:
                self.gcode.respond_info('\nApplying device configuration...')
                self._apply_discovered_devices(discovered)
                self.gcode.respond_info('Device configuration applied successfully!')
                self.gcode.respond_info('Devices will reconnect automatically.')

        except Exception as e:
            logging.error(f'ACE_SCAN_DEVICES error: {e}')
            import traceback
            logging.error(traceback.format_exc())
            raise gcmd.error(f'Failed to scan devices: {e}')

    def cmd_ACE_LIST_DEVICES(self, gcmd):
        """
        ACE_LIST_DEVICES

        List all currently connected ACE devices.
        """
        status = self.device_manager.get_aggregated_status()

        self.gcode.respond_info(f'=== Connected ACE Devices ({status["num_devices"]}) ===')

        for i, dev in enumerate(status['devices']):
            conn = '✓ Connected' if dev['connected'] else '✗ Disconnected'
            gates_str = f"{dev['gate_offset']}-{dev['gate_offset']+3}"

            self.gcode.respond_info(f'\nDevice {i+1}: {dev["name"]}')
            self.gcode.respond_info(f'  Status: {conn}')
            self.gcode.respond_info(f'  Port: {dev.get("port", "N/A")}')
            self.gcode.respond_info(f'  Gates: {gates_str}')
            if dev.get('device_id'):
                self.gcode.respond_info(f'  ID: {dev["device_id"]}')

    def cmd_ACE_SHOW_USB_INFO(self, gcmd):
        """
        ACE_SHOW_USB_INFO

        Show USB topology and device-to-port mapping.
        """
        try:
            self.gcode.respond_info('=== USB Device Mapping ===\n')

            # Show currently configured devices
            status = self.device_manager.get_aggregated_status()
            self.gcode.respond_info(f'Configured Devices: {status["num_devices"]}')

            for i, dev in enumerate(status['devices']):
                self.gcode.respond_info(f'\n{dev["name"]}:')
                self.gcode.respond_info(f'  Port: {dev.get("port", "N/A")}')
                self.gcode.respond_info(f'  Gates: {dev["gate_offset"]}-{dev["gate_offset"]+3}')
                self.gcode.respond_info(f'  USB Location: {dev.get("usb_location", "Unknown")}')
                self.gcode.respond_info(f'  Connection: {"✓ Active" if dev["connected"] else "✗ Inactive"}')

            # Scan for all ACE devices
            self.gcode.respond_info('\n=== USB Scan Results ===')
            self.gcode.respond_info('(Scanning USB ports...)')

            discovered = AceDeviceDiscovery.find_ace_devices()

            if discovered:
                self.gcode.respond_info(f'Found {len(discovered)} ACE device(s) on USB:')
                for dev in discovered:
                    self.gcode.respond_info(f'  - {dev["port"]} ({dev["device_id"]})')
            else:
                self.gcode.respond_info('No ACE devices detected on USB')

        except Exception as e:
            logging.error(f'ACE_SHOW_USB_INFO error: {e}')
            import traceback
            logging.error(traceback.format_exc())
            raise gcmd.error(f'Failed to show USB info: {e}')
