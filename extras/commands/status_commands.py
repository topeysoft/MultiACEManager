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
        ACE_GET_STATUS [DEVICE=<device_id_or_alias_or_index>] [VERBOSE=<0|1>]

        Display ACE system status.

        Options:
            DEVICE - Show details for specific device only
                     Can be: device_id (hub_1_port_2), alias (ACE1), or index (0-3)
            VERBOSE - Show detailed gate information (default: 0)

        Examples:
            ACE_GET_STATUS                    # Show summary
            ACE_GET_STATUS VERBOSE=1          # Show detailed info
            ACE_GET_STATUS DEVICE=0           # Show device 0 by index
            ACE_GET_STATUS DEVICE=ACE1        # Show device by alias
            ACE_GET_STATUS DEVICE=hub_1_port_2  # Show device by ID
        """
        device_param = gcmd.get('DEVICE', None)
        verbose = gcmd.get_int('VERBOSE', 0)

        status = self.device_manager.get_aggregated_status()

        # Resolve device filter (supports index, device_id, or alias)
        device_filter_index = None
        if device_param is not None:
            # Try parsing as integer index first
            try:
                device_filter_index = int(device_param)
                if device_filter_index < 0 or device_filter_index >= status["num_devices"]:
                    raise gcmd.error(f'Invalid device index (valid: 0-{status["num_devices"]-1})')
            except ValueError:
                # Not an integer, treat as device_id or alias
                if hasattr(self.device_manager, 'device_mapper'):
                    device_id = self.device_manager.device_mapper.resolve_device_id(device_param)
                    if not device_id:
                        raise gcmd.error(f'Device "{device_param}" not found')

                    # Find index of this device in status
                    for i, dev in enumerate(status['devices']):
                        if dev.get('device_id') == device_id:
                            device_filter_index = i
                            break

                    if device_filter_index is None:
                        raise gcmd.error(f'Device "{device_param}" not connected')
                else:
                    raise gcmd.error(f'Unable to resolve device "{device_param}"')

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
            if device_filter_index is not None and i != device_filter_index:
                continue

            conn_status = '✓' if dev['connected'] else '✗'
            gates_str = f"{dev['gate_offset']}-{dev['gate_offset']+3}"

            # Get display name (with alias if available)
            device_id = dev.get('device_id')
            display_name = dev["name"]
            if device_id and hasattr(self.device_manager, 'device_mapper'):
                alias = self.device_manager.device_mapper.get_alias(device_id)
                if alias:
                    display_name = f'{alias} ({dev["name"]})'

            self.gcode.respond_info(f"{conn_status} {display_name}: Gates {gates_str}")

            # Show detailed info if verbose or filtering
            if verbose or device_filter_index is not None:
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
                    'port': probe_result['port'],  # by-path
                    'port_tty': probe_result.get('port_tty'),  # ttyACM reference
                    'usb_location': usb_location or '',
                    'firmware': probe_result.get('firmware', 'unknown'),
                    'model': probe_result.get('model', 'ACE')
                })
                logging.info(f"StatusCommands: Verified device {probe_result['device_id']}")
                logging.info(f"StatusCommands:   by-path: {probe_result['port']}")

        # Sort by USB location for deterministic ordering
        verified_devices.sort(key=lambda d: d.get('usb_location', ''))

        # Create device instances
        from ..device.ace_device import AceDevice
        for i, dev in enumerate(verified_devices):
            device_id = dev['device_id']
            port = dev['port']  # by-path
            gate_offset = i * GATES_PER_ACE

            # Create AceDevice instance (port is already by-path)
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
                'port': port,  # by-path
                'port_tty': dev.get('port_tty', ''),  # ttyACM reference
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
                    dev_info['port'],  # by-path
                    dev_info.get('usb_location'),
                    dev_info['gate_offset'],
                    dev_info.get('port_tty')  # ttyACM reference
                )
            self.device_manager.device_mapper.save()

        # Reconnect all devices
        self.device_manager.connect_all()

        # Wait for all devices to connect (with timeout)
        self.gcode.respond_info('Waiting for devices to connect...')
        timeout = 15.0  # 15 second timeout
        start_time = self.controller.reactor.monotonic()
        poll_interval = 0.5  # Check every 500ms

        while True:
            # Check if all devices are connected
            all_connected = all(
                dev['instance']._connected
                for dev in self.device_manager.ace_devices
            )

            if all_connected:
                self.gcode.respond_info(f'All {len(verified_devices)} devices connected successfully!')
                break

            # Check timeout
            elapsed = self.controller.reactor.monotonic() - start_time
            if elapsed > timeout:
                # Count how many are actually connected
                connected_count = sum(
                    1 for dev in self.device_manager.ace_devices
                    if dev['instance']._connected
                )
                self.gcode.respond_info(
                    f'Timeout: {connected_count}/{len(verified_devices)} devices connected after {timeout}s'
                )
                break

            # Wait before next check
            currTs = self.controller.reactor.monotonic()
            self.controller.reactor.pause(currTs + poll_interval)

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

            # Get alias if available
            device_id = dev.get('device_id')
            display_name = dev["name"]
            if device_id and hasattr(self.device_manager, 'device_mapper'):
                alias = self.device_manager.device_mapper.get_alias(device_id)
                if alias:
                    display_name = f'{alias} ({dev["name"]})'

            self.gcode.respond_info(f'\nDevice {i+1}: {display_name}')
            self.gcode.respond_info(f'  Status: {conn}')
            self.gcode.respond_info(f'  Port: {dev.get("port", "N/A")}')
            self.gcode.respond_info(f'  Gates: {gates_str}')
            if device_id:
                self.gcode.respond_info(f'  ID: {device_id}')

    def cmd_ACE_SHOW_USB_INFO(self, gcmd):
        """
        ACE_SHOW_USB_INFO

        Show USB topology and device-to-port mapping.
        """
        try:
            self.gcode.respond_info('=' * 70)
            self.gcode.respond_info('ACE USB Port Mapping & Device Topology')
            self.gcode.respond_info('=' * 70)

            # Show currently configured devices
            status = self.device_manager.get_aggregated_status()
            self.gcode.respond_info(f'\nCurrently Connected Devices:')
            self.gcode.respond_info('-' * 70)

            device_mapper = None
            if hasattr(self.device_manager, 'device_mapper'):
                device_mapper = self.device_manager.device_mapper

            for i, dev in enumerate(status['devices']):
                conn_symbol = '✓' if dev['connected'] else '✗'
                device_id = dev.get('device_id', 'Unknown')

                # Get alias if available
                alias = ''
                if device_mapper and device_id != 'Unknown':
                    alias = device_mapper.get_alias(device_id)

                # Build header line
                device_num = f'Device {i+1}'
                if alias:
                    header = f'{conn_symbol} {device_num}: {alias}'
                else:
                    header = f'{conn_symbol} {device_num}: {dev["name"]}'

                self.gcode.respond_info(f'\n{header}')
                self.gcode.respond_info(f'   ID:           {device_id}')
                if alias:
                    self.gcode.respond_info(f'   Alias:        {alias}')
                self.gcode.respond_info(f'   USB Location: {dev.get("usb_location", "Unknown")}')

                # Show port information (port is now by-path)
                port = dev.get("port", "N/A")
                port_tty = dev.get("port_tty", "")

                self.gcode.respond_info(f'   Serial Path:  {port}')
                if port_tty:
                    self.gcode.respond_info(f'   TTY (ref):    {port_tty}')

                self.gcode.respond_info(f'   Gate Range:   {dev["gate_offset"]}-{dev["gate_offset"]+3}')

            # Show disconnected devices from mapper
            if device_mapper:
                all_devices = device_mapper.get_all_devices()
                connected_ids = {dev.get('device_id') for dev in status['devices']}
                disconnected = {did: info for did, info in all_devices.items() if did not in connected_ids}

                if disconnected:
                    self.gcode.respond_info('')
                    self.gcode.respond_info('=' * 70)
                    self.gcode.respond_info('Previously Seen Devices (Not Currently Connected):')
                    self.gcode.respond_info('-' * 70)

                    for device_id, info in disconnected.items():
                        alias = info.get('alias', '')
                        header = f'⊗ Device: {alias}' if alias else f'⊗ Device: {device_id}'

                        self.gcode.respond_info(f'\n{header}')
                        self.gcode.respond_info(f'   ID:              {device_id}')
                        if alias:
                            self.gcode.respond_info(f'   Alias:           {alias}')
                        self.gcode.respond_info(f'   USB Location:    {info.get("usb_location", "Unknown")}')

                        # Show port (now by-path)
                        port = info.get('port', 'Unknown')
                        port_tty = info.get('port_tty', '')
                        self.gcode.respond_info(f'   Last Path:       {port}')
                        if port_tty:
                            self.gcode.respond_info(f'   Last TTY:        {port_tty}')

                        self.gcode.respond_info(f'   Last Gate Range: {info.get("last_gate_offset", 0)}-{info.get("last_gate_offset", 0)+3}')

            # Summary
            self.gcode.respond_info('')
            self.gcode.respond_info('=' * 70)
            self.gcode.respond_info('Summary:')
            self.gcode.respond_info('-' * 70)
            self.gcode.respond_info(f'Total Connected Devices:  {status["num_devices"]}')
            self.gcode.respond_info(f'Total Gates Available:    {status["total_gates"]}')
            if device_mapper:
                total_known = len(device_mapper.get_all_devices())
                disconnected_count = len(disconnected) if 'disconnected' in locals() else 0
                self.gcode.respond_info(f'Known Devices (Total):    {total_known}')
                self.gcode.respond_info(f'Disconnected Devices:     {disconnected_count}')
            self.gcode.respond_info('')
            self.gcode.respond_info('=' * 70)
            self.gcode.respond_info('Device properties (colors, materials, temps) persist with each device')
            self.gcode.respond_info('Gate offsets are dynamically assigned based on connected device order')
            self.gcode.respond_info('')
            self.gcode.respond_info('Serial Path: All devices use /dev/serial/by-path/ for reliable')
            self.gcode.respond_info('             connections that survive reboots and port reordering')
            self.gcode.respond_info('=' * 70)

        except Exception as e:
            logging.error(f'ACE_SHOW_USB_INFO error: {e}')
            import traceback
            logging.error(traceback.format_exc())
            raise gcmd.error(f'Failed to show USB info: {e}')
