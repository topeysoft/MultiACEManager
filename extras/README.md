# ACE Pro - Modular Architecture

## Overview

ACE Pro is a multi-material system for Klipper supporting 0-4 ACE devices with 4 gates each (up to 16 total gates).

This is a **fully modular architecture** with clean separation of concerns.

## Architecture

```
AceController (business logic)
    ↓
AceDeviceManager (device pool management)
    ↓
AceDevice (hardware driver)
```

### File Structure

```
ace/
├── __init__.py               # Entry point (load_config)
├── ace_controller.py         # Main orchestration layer
├── exceptions.py             # Custom exceptions
├── protocol/                 # Protocol layer (isolated, reusable)
│   ├── constants.py
│   └── packet.py
├── device/                   # Hardware abstraction layer
│   ├── ace_device.py
│   ├── device_manager.py
│   ├── device_discovery.py
│   └── device_mapper.py
├── sensors/                  # Sensor management
│   └── runout_helper.py
└── commands/                 # G-code command handlers
    ├── tool_commands.py
    ├── config_commands.py
    └── status_commands.py
```

## Installation

```bash
cd ~/KlipperACE
./install.sh
```

This creates symlinks in `~/klipper/klippy/extras/ace/` pointing to the modular architecture.

## Configuration

Add to your `printer.cfg`:

```ini
[include ace.cfg]
```

Or for auto-detection:

```ini
[include ace_manager_auto_detect.cfg]
```

## Key Features

- **Modular**: 18 files organized by responsibility
- **Testable**: Each module can be unit tested
- **Clean**: Clear separation of protocol, hardware, business logic
- **Extensible**: Easy to add new commands or features

## Available Commands

- `ACE_CHANGE_TOOL TOOL=<n>` - Change to tool n
- `ACE_GET_STATUS [VERBOSE=1]` - Display system status
- `ACE_FEED INDEX=<n> LENGTH=<mm> [SPEED=<mm/s>]` - Feed filament
- `ACE_RETRACT INDEX=<n> LENGTH=<mm> [SPEED=<mm/s>]` - Retract filament
- `ACE_GATE_MAP GATE=<n> [COLOR=<hex>] [TYPE=<material>] [TEMP=<temp>]` - Configure gate
- `ACE_ENDLESS_SPOOL [ENABLE=<0|1>]` - Enable/disable endless spool

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture documentation
- [REFACTORING_STATUS.md](REFACTORING_STATUS.md) - Refactoring progress and metrics

## Version

**2.0.0** - Modular architecture
