# ACE Pro Migration Guide

## Overview

The ACE Pro system has been fully migrated to a modular architecture. This guide is for reference to understand the changes from the legacy monolithic `ace.py` to the new architecture.

## Architecture Evolution

### Old Architecture (Legacy - Deprecated)
- Single 4642-line `ace.py` file
- Mixed responsibilities: hardware, business logic, sensors, commands
- Difficult to test and maintain

### Current Architecture (Modular - v2.0.0+)
```
AceController (business logic)
    ↓
AceDeviceManager (device pool management)
    ↓
AceDevice (hardware driver)
```

**Key Components:**
- **protocol/** - Packet encoding/decoding, constants, CRC calculation
- **device/** - Hardware drivers, device discovery, persistent mapping
- **sensors/** - Shared filament sensor handling
- **commands/** - Tool changes, configuration, status commands
- **ace_controller.py** - Main orchestration layer (289 lines)
- **exceptions.py** - Custom exceptions

## Current Installation

As of v2.0.0 (November 2025), the system **only uses the modular architecture**. No migration steps are needed - simply install and configure as normal.

## Configuration

Standard configuration - no special flags needed:

```ini
[ace]
# Device discovery
#serial: /dev/ttyACM0              # Single device (manual)
#serial: /dev/ttyACM0,/dev/ttyACM1 # Multiple devices (manual)
# OR use auto-detection (recommended):
auto_detect: True

# Tool change speeds
feed_speed: 50
retract_speed: 50
toolchange_retract_length: 100
toolchange_feed_length: 100

# Sensor configuration
extruder_sensor_pin: ^PC5
toolhead_sensor_pin: ^PB7
toolhead_sensor_to_nozzle: 62

# Optional: Logging level
log_level: INFO  # ERROR, INFO, or DEBUG

# Optional: Connection retry settings
connect_retry_delay: 2.0
connect_retry_max: 10
```

## G-code Commands

All existing G-code commands remain the same:

### Tool Changes
- `T0`, `T1`, `T2`, ... `T15` - Change to tool N
- `ACE_CHANGE_TOOL TOOL=N` - Change to tool N

### Manual Control
- `ACE_FEED GATE=N` - Feed filament from gate N
- `ACE_RETRACT GATE=N` - Retract filament from gate N
- `ACE_UNLOAD` - Unload current filament

### Configuration
- `ACE_MAP_GATE GATE=N COLOR=RRGGBB MATERIAL=PLA TEMP=220` - Configure gate
- `ACE_ENDLESS_SPOOL_GROUPS GROUPS="0,1|2,3|4"` - Configure endless spool

### Status & Diagnostics
- `ACE_STATUS` - Show all devices and gates
- `ACE_STATUS DEVICE=0` - Show specific device
- `ACE_STATUS GATE=5` - Show specific gate

### Dryer Control
- `ACE_SET_DRYER_TEMP GATE=N TEMP=50` - Set dryer temperature
- `ACE_DRYER_ON GATE=N` - Turn on dryer
- `ACE_DRYER_OFF GATE=N` - Turn off dryer

## What Improved?

### 📊 Code Metrics
- **Files**: 1 monolithic → 18 modular files
- **Largest file**: 4642 lines → 550 lines (88% reduction)
- **Controller**: 289 lines (vs 4642 lines)
- **Testable units**: 1 class → 11+ classes

### 🏗️ Architecture Benefits
- **Separation of concerns**: Protocol, device, sensors, commands, controller
- **Reusable components**: Protocol layer can be used independently
- **Better testing**: Each layer can be tested in isolation
- **Cleaner imports**: No circular dependencies
- **Easier maintenance**: Find and fix bugs faster

### 🔧 Installation
- Single `ace/` package installed via `install.sh`
- All files symlinked to `~/klipper/klippy/extras/ace/`
- Single entry point: `ace/__init__.py`

## Troubleshooting

### Configuration Issues

If you see errors during startup:

1. **Check Klipper logs:**
   ```bash
   tail -f ~/printer_data/logs/klippy.log
   ```

2. **Verify installation:**
   ```bash
   ls -la ~/klipper/klippy/extras/ace/
   ```
   Should show symlinks to `~/KlipperACE/extras/`

3. **Check configuration:**
   - Remove any `use_new_architecture` lines (no longer needed)
   - Verify sensor pins are correct
   - Verify serial ports or `auto_detect: True`

### Device Detection Issues

If ACE devices aren't detected:

1. **Check USB connections:**
   ```bash
   ls /dev/ttyACM*
   lsusb | grep -i ace
   ```

2. **Enable debug logging:**
   ```ini
   [ace]
   log_level: DEBUG
   auto_detect: True
   ```

3. **Check logs for device discovery:**
   ```bash
   grep -i "ace.*discover" ~/printer_data/logs/klippy.log
   ```

## Architecture Reference

### Module Hierarchy

```
ace/
├── __init__.py                    # Entry point (load_config)
├── exceptions.py                  # Custom exceptions
├── ace_controller.py             # Main orchestration
├── protocol/
│   ├── constants.py              # Protocol constants
│   └── packet.py                 # Packet encoding/decoding
├── device/
│   ├── ace_device.py             # Hardware driver
│   ├── device_manager.py         # Multi-device pool
│   ├── device_discovery.py       # USB auto-detection
│   └── device_mapper.py          # Persistent device tracking
├── sensors/
│   └── runout_helper.py          # Filament sensors
└── commands/
    ├── tool_commands.py          # Tool changes
    ├── config_commands.py        # Configuration
    └── status_commands.py        # Status display
```

### Component Responsibilities

**Protocol Layer** (isolated, reusable):
- Constants and protocol definitions
- Packet encoding/decoding
- CRC calculation

**Device Layer** (hardware abstraction):
- Pure hardware driver (serial communication)
- Multi-device pool management
- USB auto-detection
- Persistent device tracking

**Sensors Layer**:
- Filament sensor management
- Runout detection
- Sensor event handling

**Commands Layer** (organized by category):
- Tool change orchestration
- Configuration management
- Status and diagnostics

**Controller Layer**:
- Main orchestration
- Coordinate between layers
- Handle Klipper events

## Support

For issues or questions:
- Check [TROUBLESHOOTING.md](../TROUBLESHOOTING.md)
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for design details
- Open an issue on GitHub

---

*Last Updated: 2025-12-03 (v2.0.0)*
