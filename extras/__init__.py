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

For backward compatibility, the original ace.py is still available.
New installations should use the modular architecture.
"""

__version__ = "2.0.0"

# Import main components for easy access
from .exceptions import AceException
from .device import AceDevice, AceDeviceManager, AceDeviceDiscovery, AceDeviceMapper
from .sensors import MmuRunoutHelper
from .protocol import constants as protocol_constants

# Import AceController for new modular architecture
from .ace_controller import AceController

# Backward compatibility: Import from original ace.py
# This allows existing configs to continue working
try:
    from .ace import load_config as load_config_legacy
    from .ace import load_config_prefix as load_config_prefix_legacy
except ImportError:
    load_config_legacy = None
    load_config_prefix_legacy = None


def load_config(config):
    """
    Klipper entry point for [ace] section.

    Supports both legacy (ace.py) and new modular architecture (AceController).

    To use the new architecture, add to your config:
        [ace]
        use_new_architecture: True

    To use legacy (default):
        [ace]
        use_new_architecture: False   # or omit entirely
    """
    # Check if user wants to use new architecture
    use_new = config.getboolean('use_new_architecture', False)

    if use_new:
        # Use new modular architecture
        return AceController(config)
    else:
        # Use legacy ace.py for backward compatibility
        if load_config_legacy:
            return load_config_legacy(config)
        else:
            raise config.error("ACE module not properly installed")


def load_config_prefix(config):
    """
    Klipper entry point for [ace <name>] sections.

    Uses the original ace.py for backward compatibility.
    Named sections currently only supported in legacy mode.
    """
    if load_config_prefix_legacy:
        return load_config_prefix_legacy(config)
    else:
        raise config.error("ACE module not properly installed")
