"""
Persistent device property management for ACE devices.
Maps device IDs (USB location) to persistent configuration (colors, materials, temps).
"""

import os
import time
import logging
import configparser
import json

from .device_discovery import AceDeviceDiscovery


class AceDeviceMapper:
    """
    Manages persistent device properties mapped by device ID (USB location).
    Gate offsets are dynamically assigned at runtime based on currently connected devices.
    Device properties (colors, materials, temps) persist with the device regardless of gate assignment.
    """

    def __init__(self, config_path):
        """
        Initialize device mapper.

        Args:
            config_path: Path to configuration file for persisting device mappings
        """
        self.config_path = config_path
        self.device_map = {}  # device_id -> {port, usb_location, alias, properties, last_seen, last_gate_offset}
        self.alias_to_id = {}  # alias -> device_id (for fast lookup)
        self.load()

    def load(self):
        """Load device map and properties from file"""
        if not os.path.exists(self.config_path):
            return

        parser = configparser.ConfigParser()
        parser.read(self.config_path)

        # Load device metadata from main section (backward compatible)
        if parser.has_section('ace_device_map'):
            for device_id_raw, value in parser.items('ace_device_map'):
                if device_id_raw.startswith('#'):
                    continue
                # Sanitize device_id when loading (handles migration from old unsanitized IDs)
                device_id = AceDeviceDiscovery.sanitize_device_id(device_id_raw)
                parts = [p.strip() for p in value.split(',')]
                if len(parts) >= 2:
                    alias = parts[4] if len(parts) > 4 else ''
                    port_tty = parts[5] if len(parts) > 5 else ''  # Legacy ttyACM for reference
                    self.device_map[device_id] = {
                        'port': parts[0],  # This is now always by-path
                        'port_tty': port_tty,  # ttyACM for reference only
                        'usb_location': parts[3] if len(parts) > 3 else '',
                        'last_seen': int(parts[2]) if len(parts) > 2 else 0,
                        'last_gate_offset': int(parts[1]) if len(parts) > 1 else 0,  # Informational only
                        'alias': alias,
                        'properties': {}
                    }
                    # Build alias lookup
                    if alias:
                        self.alias_to_id[alias] = device_id

        # Load device-specific properties from individual sections
        for section in parser.sections():
            if section.startswith('device:'):
                device_id_raw = section[7:]  # Remove 'device:' prefix
                # Sanitize device_id when loading (handles migration from old unsanitized IDs)
                device_id = AceDeviceDiscovery.sanitize_device_id(device_id_raw)
                if device_id not in self.device_map:
                    self.device_map[device_id] = {
                        'port': '',  # by-path
                        'port_tty': '',  # ttyACM reference
                        'usb_location': '',
                        'last_seen': 0,
                        'last_gate_offset': 0,
                        'alias': '',
                        'properties': {}
                    }

                # Load properties
                props = {}
                for key, value in parser.items(section):
                    try:
                        # Try to parse as JSON for lists
                        props[key] = json.loads(value)
                    except (json.JSONDecodeError, ValueError):
                        # Store as string if not JSON
                        props[key] = value

                self.device_map[device_id]['properties'] = props

    def save(self):
        """Save device map and properties to file"""
        parser = configparser.ConfigParser()

        # Save main device mapping section
        parser.add_section('ace_device_map')
        for device_id, info in sorted(self.device_map.items()):
            # Sanitize device_id for use as config option name
            safe_id = AceDeviceDiscovery.sanitize_device_id(device_id)
            alias = info.get('alias', '')
            port_tty = info.get('port_tty', '')
            # Format: port(by-path), gate_offset, timestamp, usb_location, alias, port_tty(reference)
            value = f"{info['port']}, {info['last_gate_offset']}, {int(time.time())}, {info.get('usb_location', '')}, {alias}, {port_tty}"
            parser.set('ace_device_map', safe_id, value)

        # Save device-specific properties in separate sections
        for device_id, info in sorted(self.device_map.items()):
            if info.get('properties'):
                # Sanitize device_id for use as section name
                safe_id = AceDeviceDiscovery.sanitize_device_id(device_id)
                section_name = f'device:{safe_id}'
                parser.add_section(section_name)
                for prop_key, prop_value in info['properties'].items():
                    # Serialize lists/dicts as JSON
                    if isinstance(prop_value, (list, dict)):
                        value_str = json.dumps(prop_value)
                    else:
                        value_str = str(prop_value)
                    parser.set(section_name, prop_key, value_str)

        # Write with header comment
        with open(self.config_path, 'w') as f:
            f.write('# Auto-generated by ACE Manager - DO NOT EDIT MANUALLY\n')
            f.write('# This file stores device properties by USB port location\n')
            f.write('# Gate offsets are dynamically assigned based on currently connected devices\n')
            f.write('# Device properties (colors, materials, temps) persist with the device\n\n')
            parser.write(f)

    def update_device(self, device_id, port, usb_location=None, current_gate_offset=None, port_tty=None):
        """Update or add a device mapping. Port is always by-path."""
        if device_id not in self.device_map:
            self.device_map[device_id] = {
                'port': port,  # by-path
                'port_tty': port_tty or '',  # ttyACM reference
                'usb_location': usb_location or '',
                'last_seen': int(time.time()),
                'last_gate_offset': current_gate_offset if current_gate_offset is not None else 0,
                'alias': '',
                'properties': {}
            }
        else:
            self.device_map[device_id]['port'] = port
            self.device_map[device_id]['usb_location'] = usb_location or self.device_map[device_id].get('usb_location', '')
            self.device_map[device_id]['last_seen'] = int(time.time())
            if current_gate_offset is not None:
                self.device_map[device_id]['last_gate_offset'] = current_gate_offset
            # Update tty reference if provided
            if port_tty is not None:
                self.device_map[device_id]['port_tty'] = port_tty

    def get_device_properties(self, device_id):
        """Get properties for a device"""
        return self.device_map.get(device_id, {}).get('properties', {})

    def update_device_properties(self, device_id, properties):
        """Update properties for a device"""
        if device_id in self.device_map:
            self.device_map[device_id]['properties'].update(properties)
        else:
            logging.warning(f"ACE Mapper: Tried to update properties for unknown device {device_id}")

    def get_device_info(self, device_id):
        """Get full device info"""
        return self.device_map.get(device_id, {})

    def get_all_devices(self):
        """Get all known devices"""
        return self.device_map.copy()

    def find_device_by_port(self, port):
        """Find device ID by current port"""
        for device_id, info in self.device_map.items():
            if info['port'] == port:
                return device_id
        return None

    def resolve_device_id(self, identifier):
        """
        Resolve device identifier to device_id.
        Accepts either device_id or alias.

        Args:
            identifier: Device ID (e.g., 'hub_1_port_2') or alias (e.g., 'ACE1', 'top_left')

        Returns:
            device_id if found, None otherwise
        """
        # First check if it's an alias
        if identifier in self.alias_to_id:
            return self.alias_to_id[identifier]

        # Check if it's a device_id
        if identifier in self.device_map:
            return identifier

        return None

    def set_alias(self, device_id, alias):
        """
        Set or update alias for a device.

        Args:
            device_id: Device ID to set alias for
            alias: New alias (empty string to remove alias)

        Returns:
            True if successful, False if device not found or alias already in use
        """
        if device_id not in self.device_map:
            logging.warning(f"ACE Mapper: Cannot set alias for unknown device {device_id}")
            return False

        # Check if alias is already in use by another device
        if alias and alias in self.alias_to_id and self.alias_to_id[alias] != device_id:
            logging.warning(f"ACE Mapper: Alias '{alias}' already in use by device {self.alias_to_id[alias]}")
            return False

        # Remove old alias if exists
        old_alias = self.device_map[device_id].get('alias', '')
        if old_alias and old_alias in self.alias_to_id:
            del self.alias_to_id[old_alias]

        # Set new alias
        self.device_map[device_id]['alias'] = alias
        if alias:
            self.alias_to_id[alias] = device_id
            logging.info(f"ACE Mapper: Set alias '{alias}' for device {device_id}")
        else:
            logging.info(f"ACE Mapper: Removed alias from device {device_id}")

        return True

    def get_alias(self, device_id):
        """Get alias for a device (returns empty string if no alias)"""
        return self.device_map.get(device_id, {}).get('alias', '')

    def get_display_name(self, device_id):
        """Get display name for device (alias if set, otherwise device_id)"""
        alias = self.get_alias(device_id)
        return alias if alias else device_id

    def get_all_aliases(self):
        """
        Get all defined aliases.

        Returns:
            dict: Dictionary mapping alias -> device_id for all aliases
        """
        return self.alias_to_id.copy()
