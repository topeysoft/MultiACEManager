# ACE Manager Moonraker Component
#
# Copyright (C) 2025 Temi Oyelade <temi@example.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import logging
import asyncio
import json
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from confighelper import ConfigHelper
    from websockets import WebRequest

class AceManager:
    """
    Moonraker component for ACE Pro device management.

    Provides REST API endpoints for multi-device ACE Pro management,
    including device discovery, status monitoring, and gate reordering.
    """

    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.klippy_apis = self.server.lookup_component('klippy_apis')

        # Register API endpoints
        self.server.register_endpoint(
            "/server/ace/devices",
            ['GET'],
            self._handle_get_devices,
            transports=['http', 'websocket']
        )

        self.server.register_endpoint(
            "/server/ace/scan",
            ['POST'],
            self._handle_scan_devices,
            transports=['http', 'websocket']
        )

        self.server.register_endpoint(
            "/server/ace/reorder",
            ['POST'],
            self._handle_reorder_devices,
            transports=['http', 'websocket']
        )

        self.server.register_endpoint(
            "/server/ace/status",
            ['GET'],
            self._handle_get_status,
            transports=['http', 'websocket']
        )

        logging.info("ACE Manager Moonraker component initialized")

    async def _handle_get_devices(self, web_request: WebRequest) -> Dict[str, Any]:
        """
        GET /server/ace/devices

        Returns detailed information about all ACE devices.

        Response:
        {
            "devices": [
                {
                    "device_id": "mac_001a2b3c",
                    "name": "ACE Unit 1",
                    "port": "/dev/ttyACM0",
                    "model": "ACE PRO",
                    "firmware": "v2.1.0",
                    "connection_status": "connected",
                    "gate_offset": 0,
                    "num_gates": 4,
                    "gates": [0, 1, 2, 3],
                    "health": {
                        "avg_response_time_ms": 45,
                        "error_count": 0,
                        "uptime": 3600
                    }
                },
                ...
            ],
            "total_gates": 8,
            "auto_detect_enabled": true
        }
        """
        try:
            # Query the ACE Manager object in Klipper
            result = await self.klippy_apis.query_objects({'ace': None})

            if 'ace' not in result:
                return {
                    'error': 'ACE Manager not found in Klipper',
                    'devices': [],
                    'total_gates': 0
                }

            ace_data = result['ace']

            # Build response with device information
            devices = ace_data.get('devices', [])

            return {
                'devices': devices,
                'total_gates': ace_data.get('num_gates', 0),
                'num_devices': ace_data.get('num_devices', 0),
                'auto_detect_enabled': True
            }

        except Exception as e:
            logging.exception(f"Error getting ACE devices: {e}")
            return {
                'error': str(e),
                'devices': [],
                'total_gates': 0
            }

    async def _handle_scan_devices(self, web_request: WebRequest) -> Dict[str, Any]:
        """
        POST /server/ace/scan

        Triggers a manual device scan.

        Request Body:
        {
            "rescan": true,       # Optional, default true
            "update_map": true    # Optional, default true
        }

        Response:
        {
            "status": "success",
            "devices_found": 2,
            "new_devices": 0,
            "devices": {...}
        }
        """
        try:
            args = web_request.get_args()
            rescan = args.get('rescan', True)
            update_map = args.get('update_map', True)

            # Execute ACE_SCAN_DEVICES GCode command
            script = 'ACE_SCAN_DEVICES'
            await self.klippy_apis.run_gcode(script)

            # Wait a moment for scan to complete
            await asyncio.sleep(1.0)

            # Get updated device list
            result = await self.klippy_apis.query_objects({'ace': None})

            if 'ace' not in result:
                return {
                    'status': 'error',
                    'message': 'ACE Manager not found'
                }

            ace_data = result['ace']
            devices = ace_data.get('devices', [])

            return {
                'status': 'success',
                'devices_found': len(devices),
                'new_devices': 0,  # Would need to track this from scan
                'devices': devices
            }

        except Exception as e:
            logging.exception(f"Error scanning ACE devices: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def _handle_reorder_devices(self, web_request: WebRequest) -> Dict[str, Any]:
        """
        POST /server/ace/reorder

        Reorders gate assignments for devices.

        Request Body:
        {
            "device_order": [
                {"device_id": "mac_001a2b3c", "gate_offset": 0},
                {"device_id": "mac_00aabbcc", "gate_offset": 4}
            ]
        }

        Response:
        {
            "status": "success",
            "message": "Gate assignments updated. Restart required.",
            "restart_required": true
        }
        """
        try:
            args = web_request.get_args()
            device_order = args.get('device_order', [])

            if not device_order:
                return {
                    'status': 'error',
                    'message': 'device_order is required'
                }

            # For now, we'll need to implement this via a custom GCode command
            # that calls the Python reorder_gates method

            # Build GCode command with JSON-encoded device order
            device_order_json = json.dumps(device_order)

            # This would require a new GCode command like:
            # ACE_REORDER_DEVICES ORDER='[...]'
            script = f'ACE_REORDER_DEVICES ORDER=\'{device_order_json}\''

            try:
                await self.klippy_apis.run_gcode(script)

                return {
                    'status': 'success',
                    'message': 'Gate assignments updated. Restart Klipper to apply changes.',
                    'restart_required': True
                }
            except Exception as gcode_error:
                # If the command doesn't exist yet, return helpful error
                return {
                    'status': 'error',
                    'message': f'ACE_REORDER_DEVICES command not implemented: {gcode_error}'
                }

        except Exception as e:
            logging.exception(f"Error reordering ACE devices: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    async def _handle_get_status(self, web_request: WebRequest) -> Dict[str, Any]:
        """
        GET /server/ace/status

        Returns the current ACE Manager status including all gates and devices.

        Response:
        {
            "status": "ready",
            "temp": 25,
            "num_gates": 8,
            "num_devices": 2,
            "gate_color": [...],
            "gate_material": [...],
            "active_gate": [...],
            "devices": [...]
        }
        """
        try:
            # Query the full ACE status object
            result = await self.klippy_apis.query_objects({'ace': None})

            if 'ace' not in result:
                return {
                    'error': 'ACE Manager not found in Klipper'
                }

            # Return the full ACE status
            return result['ace']

        except Exception as e:
            logging.exception(f"Error getting ACE status: {e}")
            return {
                'error': str(e)
            }


def load_component(config: ConfigHelper) -> AceManager:
    """
    Standard Moonraker component loader.

    This function is called by Moonraker when the component is loaded.
    """
    return AceManager(config)
