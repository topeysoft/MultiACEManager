"""
ACE Pro Multi-Material System for Klipper.

This package provides support for the ACE Pro filament management system,
supporting 0-4 ACE devices with 4 gates each (up to 16 total gates).

Architecture:
    AceController (business logic)
        ↓
    AceDeviceManager (device pool management)
        ↓
    AceDevice (hardware driver)
"""

__version__ = "2.0.0"

# Import main components for easy access
from .exceptions import AceException
from .device import AceDevice, AceDeviceManager, AceDeviceDiscovery, AceDeviceMapper
from .sensors import MmuRunoutHelper
from .protocol import constants as protocol_constants
from .ace_controller import AceController


def load_config(config):
    """
    Klipper entry point for [ace] section.

    Returns AceController instance with modular architecture.
    """
    return AceController(config)


def load_config_prefix(config):
    """
    Klipper entry point for [ace <name>] sections.

    Returns AceController instance with custom name.
    """
    return AceController(config)
