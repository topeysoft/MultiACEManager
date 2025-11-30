"""
Configuration-related G-code commands for ACE Pro system.

Commands:
- ACE_GATE_MAP - Configure gate properties (color, material, temp)
- ACE_ENDLESS_SPOOL - Enable/disable endless spool feature
- ACE_ALIAS - Set friendly alias for a device
- ACE_UNALIAS - Remove alias from a device
"""

import logging


class ConfigCommands:
    """
    Configuration and settings commands.

    This class contains all G-code commands related to configuring
    the ACE system (gate mapping, endless spool, etc).
    """

    def __init__(self, controller):
        """
        Initialize config commands.

        Args:
            controller: AceController instance
        """
        self.controller = controller
        self.gcode = controller.gcode
        self.device_manager = controller.device_manager
        self.save_variables = controller.save_variables

    def register(self):
        """Register all configuration commands"""
        self.gcode.register_command(
            'ACE_GATE_MAP', self.cmd_ACE_GATE_MAP,
            desc='Configure gate properties')

        self.gcode.register_command(
            'ACE_ENDLESS_SPOOL', self.cmd_ACE_ENDLESS_SPOOL,
            desc='Enable/disable endless spool')

        self.gcode.register_command(
            'ACE_ALIAS', self.cmd_ACE_ALIAS,
            desc='Set device alias')

        self.gcode.register_command(
            'ACE_UNALIAS', self.cmd_ACE_UNALIAS,
            desc='Remove device alias')

        logging.info("ConfigCommands: Registered ACE_GATE_MAP, ACE_ENDLESS_SPOOL, ACE_ALIAS, ACE_UNALIAS")

    def cmd_ACE_GATE_MAP(self, gcmd):
        """
        ACE_GATE_MAP GATE=<n> [COLOR=<hex>] [TYPE=<material>] [TEMP=<temp>]

        Configure gate properties.

        Examples:
            ACE_GATE_MAP GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
            ACE_GATE_MAP GATE=1 COLOR=00FF00 TYPE=PETG TEMP=240
        """
        gate = gcmd.get_int('GATE')
        color = gcmd.get('COLOR', None)
        material_type = gcmd.get('TYPE', None)
        temp = gcmd.get_int('TEMP', None)

        if gate < 0 or gate >= self.device_manager.total_gates:
            raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')

        # Update gate color
        if color:
            gate_colors = self.save_variables.allVariables.get(
                'ace_gate_color',
                ['FFFFFF'] * self.device_manager.total_gates
            )
            while len(gate_colors) < self.device_manager.total_gates:
                gate_colors.append('FFFFFF')
            gate_colors[gate] = color
            self.controller.save_variable('ace_gate_color', gate_colors, True)
            logging.info(f'ConfigCommands: Gate {gate} color set to {color}')

        # Update gate material type
        if material_type:
            gate_materials = self.save_variables.allVariables.get(
                'ace_gate_type',
                [''] * self.device_manager.total_gates
            )
            while len(gate_materials) < self.device_manager.total_gates:
                gate_materials.append('')
            gate_materials[gate] = material_type
            self.controller.save_variable('ace_gate_type', gate_materials, True)
            logging.info(f'ConfigCommands: Gate {gate} material set to {material_type}')

        # Update gate temperature
        if temp:
            gate_temps = self.save_variables.allVariables.get(
                'ace_gate_temp',
                [230] * self.device_manager.total_gates
            )
            while len(gate_temps) < self.device_manager.total_gates:
                gate_temps.append(230)
            gate_temps[gate] = temp
            self.controller.save_variable('ace_gate_temp', gate_temps, True)
            logging.info(f'ConfigCommands: Gate {gate} temp set to {temp}')

        # Build response message
        props = []
        if color:
            props.append(f'color={color}')
        if material_type:
            props.append(f'type={material_type}')
        if temp:
            props.append(f'temp={temp}')

        if props:
            self.gcode.respond_info(f'ACE: Gate {gate} configured ({", ".join(props)})')
        else:
            self.gcode.respond_info(f'ACE: No properties specified for gate {gate}')

    def cmd_ACE_ENDLESS_SPOOL(self, gcmd):
        """
        ACE_ENDLESS_SPOOL [ENABLE=<0|1>]

        Enable or disable endless spool feature.

        When enabled, the system will automatically switch to another
        gate with the same material type when a runout is detected.

        Examples:
            ACE_ENDLESS_SPOOL ENABLE=1  # Enable
            ACE_ENDLESS_SPOOL ENABLE=0  # Disable
            ACE_ENDLESS_SPOOL           # Toggle or show status
        """
        enable = gcmd.get_int('ENABLE', None)

        if enable is None:
            # No argument provided, show current status
            current = self.save_variables.allVariables.get('ace_endless_spool', False)
            status = 'enabled' if current else 'disabled'
            self.gcode.respond_info(f'ACE: Endless spool is {status}')
            return

        # Update setting
        self.controller.save_variable('ace_endless_spool', bool(enable), True)

        status = 'enabled' if enable else 'disabled'
        logging.info(f'ConfigCommands: Endless spool {status}')
        self.gcode.respond_info(f'ACE: Endless spool {status}')

    def cmd_ACE_ALIAS(self, gcmd):
        """
        ACE_ALIAS DEVICE=<device_id> NAME=<alias>

        Set a friendly alias for a device.
        The device can then be referenced by either its device_id or alias.

        Examples:
            ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE1
            ACE_ALIAS DEVICE=hub_1_port_3 NAME=top_left
            ACE_ALIAS DEVICE=hub_1_port_4 NAME=filament_tower

        After setting an alias, you can use it in commands:
            ACE_GET_STATUS DEVICE=ACE1
            ACE_GATE_MAP DEVICE=top_left GATE=0 COLOR=FF0000
        """
        device = gcmd.get('DEVICE')
        alias = gcmd.get('NAME')

        if not device:
            raise gcmd.error('DEVICE parameter required')
        if not alias:
            raise gcmd.error('NAME parameter required')

        # Validate alias format (alphanumeric and underscore only)
        if not alias.replace('_', '').isalnum():
            raise gcmd.error('Alias must contain only letters, numbers, and underscores')

        # Get device mapper
        device_mapper = self.device_manager.device_mapper

        # Resolve device (in case they're using an existing alias)
        device_id = device_mapper.resolve_device_id(device)
        if not device_id:
            raise gcmd.error(f'Device "{device}" not found')

        # Set alias
        if device_mapper.set_alias(device_id, alias):
            device_mapper.save()
            logging.info(f'ConfigCommands: Set alias "{alias}" for device {device_id}')
            self.gcode.respond_info(f'ACE: Device {device_id} aliased as "{alias}"')
        else:
            raise gcmd.error(f'Failed to set alias (may already be in use)')

    def cmd_ACE_UNALIAS(self, gcmd):
        """
        ACE_UNALIAS DEVICE=<device_id_or_alias>

        Remove the alias from a device.

        Examples:
            ACE_UNALIAS DEVICE=ACE1
            ACE_UNALIAS DEVICE=hub_1_port_2
        """
        device = gcmd.get('DEVICE')

        if not device:
            raise gcmd.error('DEVICE parameter required')

        # Get device mapper
        device_mapper = self.device_manager.device_mapper

        # Resolve device
        device_id = device_mapper.resolve_device_id(device)
        if not device_id:
            raise gcmd.error(f'Device "{device}" not found')

        # Get current alias
        old_alias = device_mapper.get_alias(device_id)
        if not old_alias:
            self.gcode.respond_info(f'ACE: Device {device_id} has no alias')
            return

        # Remove alias
        if device_mapper.set_alias(device_id, ''):
            device_mapper.save()
            logging.info(f'ConfigCommands: Removed alias "{old_alias}" from device {device_id}')
            self.gcode.respond_info(f'ACE: Removed alias "{old_alias}" from device {device_id}')
        else:
            raise gcmd.error('Failed to remove alias')
