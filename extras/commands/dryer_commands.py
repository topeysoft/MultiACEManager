"""
Dryer control G-code commands for ACE Pro system.

Commands:
- ACE_START_DRYING - Start dryer on a specific device
- ACE_STOP_DRYING - Stop dryer on a specific device
- ACE_GET_DRYER_STATUS - Display status of all dryers
"""

import logging

class DryerCommands:
    """
    Dryer control commands.

    This class contains all G-code commands related to controlling
    the dryers on ACE devices.
    """

    def __init__(self, controller):
        """
        Initialize dryer commands.

        Args:
            controller: AceController instance
        """
        self.controller = controller
        self.gcode = controller.gcode
        self.device_manager = controller.device_manager
        self.max_dryer_temperature = controller.max_dryer_temperature

    def register(self):
        """Register all dryer commands"""
        self.gcode.register_command(
            'ACE_START_DRYING', self.cmd_ACE_START_DRYING,
            desc='Start dryer on ACE device')

        self.gcode.register_command(
            'ACE_STOP_DRYING', self.cmd_ACE_STOP_DRYING,
            desc='Stop dryer on ACE device')

        self.gcode.register_command(
            'ACE_GET_DRYER_STATUS', self.cmd_ACE_GET_DRYER_STATUS,
            desc='Display dryer status for all devices')

        logging.info("DryerCommands: Registered ACE_START_DRYING, ACE_STOP_DRYING, ACE_GET_DRYER_STATUS")

    def cmd_ACE_START_DRYING(self, gcmd):
        """
        ACE_START_DRYING [DEVICE=<device_id_or_alias>] [GATE=<n>] TEMP=<temp> [DURATION=<minutes>]

        Start the dryer on a specific ACE device.

        Parameters:
            DEVICE - (Optional) Device ID, alias, or index
            GATE - (Optional) Gate number (0-15) - finds the device automatically
            TEMP - Target temperature in Celsius (required)
            DURATION - Duration in minutes (default: 240)

        Note: Either DEVICE or GATE must be specified.

        Examples:
            # By device ID
            ACE_START_DRYING DEVICE=hub_1_port_1 TEMP=60 DURATION=240

            # By alias
            ACE_START_DRYING DEVICE=ACE1 TEMP=55 DURATION=180

            # By gate number (convenience)
            ACE_START_DRYING GATE=0 TEMP=60 DURATION=240
            ACE_START_DRYING GATE=4 TEMP=55 DURATION=180
        """
        device_param = gcmd.get('DEVICE', None)
        gate_param = gcmd.get_int('GATE', None)
        temp = gcmd.get_int('TEMP')
        duration = gcmd.get_int('DURATION', 240)

        # Validate parameters
        if device_param is None and gate_param is None:
            raise gcmd.error('Either DEVICE or GATE parameter required')

        if device_param is not None and gate_param is not None:
            raise gcmd.error('Cannot specify both DEVICE and GATE parameters')

        if duration <= 0:
            raise gcmd.error('Duration must be positive')

        if temp <= 0 or temp > self.max_dryer_temperature:
            raise gcmd.error(f'Temperature must be 1-{self.max_dryer_temperature}°C')

        # Resolve device
        device = None
        if gate_param is not None:
            # Find device by gate number
            if gate_param < 0 or gate_param >= self.device_manager.total_gates:
                raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')
            device, local_gate = self.device_manager.get_device_for_gate(gate_param)
        else:
            # Find device by ID/alias/index
            status = self.device_manager.get_aggregated_status()

            # Try as index first
            try:
                device_index = int(device_param)
                if device_index < 0 or device_index >= status["num_devices"]:
                    raise gcmd.error(f'Invalid device index (valid: 0-{status["num_devices"]-1})')
                device = self.device_manager.devices[device_index]
            except ValueError:
                # Not an integer, treat as device_id or alias
                if hasattr(self.device_manager, 'device_mapper'):
                    device_id = self.device_manager.device_mapper.resolve_device_id(device_param)
                    if not device_id:
                        raise gcmd.error(f'Device "{device_param}" not found')

                    # Find the device instance
                    for dev in self.device_manager.devices:
                        if dev.device_id == device_id:
                            device = dev
                            break

                    if device is None:
                        raise gcmd.error(f'Device "{device_param}" not connected')
                else:
                    raise gcmd.error(f'Unable to resolve device "{device_param}"')

        # Start dryer
        def callback(response):
            if 'code' in response and response['code'] != 0:
                msg = response.get('msg', 'Unknown error')
                logging.error(f"DryerCommands: Failed to start dryer: {msg}")
                self.gcode.respond_info(f'ACE: Dryer start failed: {msg}')
            else:
                logging.info(f"DryerCommands: Started dryer on device {device.device_id} ({temp}°C for {duration}min)")
                self.gcode.respond_info(f'ACE: Started dryer on device {device.device_id} ({temp}°C for {duration} minutes)')

        device.start_dryer(temp, duration, callback)

    def cmd_ACE_STOP_DRYING(self, gcmd):
        """
        ACE_STOP_DRYING [DEVICE=<device_id_or_alias>] [GATE=<n>]

        Stop the dryer on a specific ACE device.

        Parameters:
            DEVICE - (Optional) Device ID, alias, or index
            GATE - (Optional) Gate number (0-15) - finds the device automatically

        Note: Either DEVICE or GATE must be specified.

        Examples:
            # By device ID
            ACE_STOP_DRYING DEVICE=hub_1_port_1

            # By alias
            ACE_STOP_DRYING DEVICE=ACE1

            # By gate number (convenience)
            ACE_STOP_DRYING GATE=0
            ACE_STOP_DRYING GATE=4
        """
        device_param = gcmd.get('DEVICE', None)
        gate_param = gcmd.get_int('GATE', None)

        # Validate parameters
        if device_param is None and gate_param is None:
            raise gcmd.error('Either DEVICE or GATE parameter required')

        if device_param is not None and gate_param is not None:
            raise gcmd.error('Cannot specify both DEVICE and GATE parameters')

        # Resolve device (same logic as start)
        device = None
        if gate_param is not None:
            # Find device by gate number
            if gate_param < 0 or gate_param >= self.device_manager.total_gates:
                raise gcmd.error(f'Invalid gate (valid: 0-{self.device_manager.total_gates-1})')
            device, local_gate = self.device_manager.get_device_for_gate(gate_param)
        else:
            # Find device by ID/alias/index
            status = self.device_manager.get_aggregated_status()

            # Try as index first
            try:
                device_index = int(device_param)
                if device_index < 0 or device_index >= status["num_devices"]:
                    raise gcmd.error(f'Invalid device index (valid: 0-{status["num_devices"]-1})')
                device = self.device_manager.devices[device_index]
            except ValueError:
                # Not an integer, treat as device_id or alias
                if hasattr(self.device_manager, 'device_mapper'):
                    device_id = self.device_manager.device_mapper.resolve_device_id(device_param)
                    if not device_id:
                        raise gcmd.error(f'Device "{device_param}" not found')

                    # Find the device instance
                    for dev in self.device_manager.devices:
                        if dev.device_id == device_id:
                            device = dev
                            break

                    if device is None:
                        raise gcmd.error(f'Device "{device_param}" not connected')
                else:
                    raise gcmd.error(f'Unable to resolve device "{device_param}"')

        # Stop dryer
        def callback(response):
            if 'code' in response and response['code'] != 0:
                msg = response.get('msg', 'Unknown error')
                logging.error(f"DryerCommands: Failed to stop dryer: {msg}")
                self.gcode.respond_info(f'ACE: Dryer stop failed: {msg}')
            else:
                logging.info(f"DryerCommands: Stopped dryer on device {device.device_id}")
                self.gcode.respond_info(f'ACE: Stopped dryer on device {device.device_id}')

        device.stop_dryer(callback)

    def cmd_ACE_GET_DRYER_STATUS(self, gcmd):
        """
        ACE_GET_DRYER_STATUS

        Display status of all dryers.

        Shows:
        - Device ID and gate range
        - Dryer status (running/stopped)
        - Current and target temperature
        - Time remaining

        Example output:
            ======================================================================
            ACE Dryer Status
            ======================================================================

            ACE Unit 1 (hub_1_port_1) - Gates 0-3:
              Status:    🔥 Running
              Current:   55°C
              Target:    60°C
              Duration:  240 minutes
              Remaining: 180 minutes

            ACE Unit 2 (hub_1_port_2) - Gates 4-7:
              Status:    ⭘ Stopped
              Current:   25°C

            ======================================================================
        """
        status = self.device_manager.get_aggregated_status()

        if status['num_devices'] == 0:
            self.gcode.respond_info('ACE: No devices connected')
            return

        # Header
        self.gcode.respond_info('=' * 70)
        self.gcode.respond_info('ACE Dryer Status')
        self.gcode.respond_info('=' * 70)
        self.gcode.respond_info('')

        # Display each device
        for i, device_info in enumerate(status['devices']):
            device_id = device_info.get('device_id', f'Device {i}')
            gate_offset = device_info['gate_offset']
            gate_range = f'{gate_offset}-{gate_offset+3}'

            # Get dryer status
            dryer_status = device_info.get('dryer_status', {})
            dryer_temp = device_info.get('dryer_temp', 0)

            self.gcode.respond_info(f'ACE Unit {i+1} ({device_id}) - Gates {gate_range}:')

            # Status
            status_str = dryer_status.get('status', 'unknown')
            if status_str == 'running':
                self.gcode.respond_info(f'  Status:    🔥 Running')
            else:
                self.gcode.respond_info(f'  Status:    ⭘ Stopped')

            # Temperature
            self.gcode.respond_info(f'  Current:   {dryer_temp}°C')

            # Additional info if running
            if status_str == 'running':
                target_temp = dryer_status.get('target_temp', 0)
                duration = dryer_status.get('duration', 0)
                remain_time = dryer_status.get('remain_time', 0)

                self.gcode.respond_info(f'  Target:    {target_temp}°C')
                self.gcode.respond_info(f'  Duration:  {duration} minutes')
                self.gcode.respond_info(f'  Remaining: {remain_time} minutes')

            self.gcode.respond_info('')

        # Footer
        self.gcode.respond_info('=' * 70)
        self.gcode.respond_info('Commands:')
        self.gcode.respond_info('  ACE_START_DRYING DEVICE=<id> TEMP=<temp> DURATION=<min>')
        self.gcode.respond_info('  ACE_START_DRYING GATE=<num> TEMP=<temp> DURATION=<min>')
        self.gcode.respond_info('  ACE_STOP_DRYING DEVICE=<id>  or  ACE_STOP_DRYING GATE=<num>')
        self.gcode.respond_info('=' * 70)
