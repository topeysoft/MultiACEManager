# ACE Installation Structure

## Overview

The ACE system uses a **modular package architecture** installed as a single `ace/` package in Klipper's extras directory.

## Installation Structure

```
~/klipper/klippy/extras/
└── ace/                                    ← Package (Klipper finds this)
    ├── __init__.py                         ← Entry point with load_config()
    ├── ace_controller.py                   ← Main orchestration layer
    ├── exceptions.py                       ← Custom exceptions
    ├── protocol/
    │   ├── __init__.py
    │   ├── constants.py                    ← Protocol constants
    │   └── packet.py                       ← Packet encoding/decoding
    ├── device/
    │   ├── __init__.py
    │   ├── ace_device.py                   ← Hardware driver
    │   ├── device_manager.py               ← Multi-device management
    │   ├── device_discovery.py             ← USB auto-detection
    │   └── device_mapper.py                ← Persistent device tracking
    ├── sensors/
    │   ├── __init__.py
    │   └── runout_helper.py                ← Filament sensor logic
    └── commands/
        ├── __init__.py
        ├── tool_commands.py                ← Tool change/feed/retract
        ├── config_commands.py              ← Gate mapping/endless spool
        └── status_commands.py              ← Status/diagnostics
```

## Installation Flow

```
./install.sh
    ↓
Creates: ~/klipper/klippy/extras/ace/
    ↓
Links all modular files:
  - ace/__init__.py       → ~/KlipperACE/extras/__init__.py
  - ace/ace_controller.py → ~/KlipperACE/extras/ace_controller.py
  - ace/protocol/*        → ~/KlipperACE/extras/protocol/*
  - ace/device/*          → ~/KlipperACE/extras/device/*
  - ace/sensors/*         → ~/KlipperACE/extras/sensors/*
  - ace/commands/*        → ~/KlipperACE/extras/commands/*
    ↓
Klipper sees: ace/ package with load_config() in __init__.py
    ↓
✅ Single entry point, modular architecture!
```

## How Klipper Loads ACE

Klipper's module loader:
1. Scans `klippy/extras/` directory
2. For each `.py` file → imports module
3. For each subdirectory with `__init__.py` → imports package
4. Calls `load_config()` when `[ace]` section found in config

**ACE structure:**
```python
# Klipper sees:
import ace  # → klippy/extras/ace/__init__.py

# When [ace] section found in config:
ace.load_config(config)  # → ace/__init__.py:load_config()
    ↓
return AceController(config)  # Modular architecture
```

## Configuration

Simple configuration in `printer.cfg`:

```ini
[ace]
serial: /dev/ttyACM0
# OR
auto_detect: True
```

No special flags needed - always uses modular architecture.

## File Locations After Install

All files are **symlinks** to `~/KlipperACE/extras/*`:

```
~/klipper/klippy/extras/ace/
├── __init__.py                         → ~/KlipperACE/extras/__init__.py
├── ace_controller.py                   → ~/KlipperACE/extras/ace_controller.py
├── exceptions.py                       → ~/KlipperACE/extras/exceptions.py
├── protocol/
│   ├── __init__.py                     → ~/KlipperACE/extras/protocol/__init__.py
│   ├── constants.py                    → ~/KlipperACE/extras/protocol/constants.py
│   └── packet.py                       → ~/KlipperACE/extras/protocol/packet.py
├── device/
│   ├── __init__.py                     → ~/KlipperACE/extras/device/__init__.py
│   ├── ace_device.py                   → ~/KlipperACE/extras/device/ace_device.py
│   ├── device_manager.py               → ~/KlipperACE/extras/device/device_manager.py
│   ├── device_discovery.py             → ~/KlipperACE/extras/device/device_discovery.py
│   └── device_mapper.py                → ~/KlipperACE/extras/device/device_mapper.py
├── sensors/
│   ├── __init__.py                     → ~/KlipperACE/extras/sensors/__init__.py
│   └── runout_helper.py                → ~/KlipperACE/extras/sensors/runout_helper.py
└── commands/
    ├── __init__.py                     → ~/KlipperACE/extras/commands/__init__.py
    ├── tool_commands.py                → ~/KlipperACE/extras/commands/tool_commands.py
    ├── config_commands.py              → ~/KlipperACE/extras/commands/config_commands.py
    └── status_commands.py              → ~/KlipperACE/extras/commands/status_commands.py
```

**Key Point**: Changes to `~/KlipperACE/extras/*` immediately apply to Klipper via symlinks.

## Architecture Benefits

### ✅ Clean Modular Structure
- Single entry point: `ace/__init__.py`
- Organized by layer: protocol, device, sensors, commands, controller
- No monolithic files

### ✅ Maintainable
- Largest file: 550 lines (was 4642 lines)
- Clear separation of concerns
- Easy to test and modify

### ✅ No Conflicts
- Single `load_config()` function
- Klipper sees one module: `ace`
- Clean Python package structure

## Summary

**Installation creates:**
```
ace/                   ← Package (Klipper entry point)
 ├── __init__.py       ← Has load_config() → returns AceController
 └── modular files     ← Protocol, Device, Sensors, Commands layers
```

**Klipper calls:**
```
ace.load_config(config)  → ace/__init__.py:load_config()
                           ↓
                   return AceController(config)
                           ↓
                   Modular architecture loads
```

**Clean, modular, maintainable!** ✅

---

*Last Updated: 2025-12-03*
