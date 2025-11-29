"""
Status and diagnostic commands for ACE Pro system.

Commands:
- ACE_GET_STATUS - Display system status
"""

import logging


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

        logging.info("StatusCommands: Registered ACE_GET_STATUS")

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
