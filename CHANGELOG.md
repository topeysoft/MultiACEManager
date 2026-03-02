# Changelog

## [2.0.0] - 2025-11-29

### 🎉 Complete Architecture Refactoring

**Breaking Changes:**
- Removed legacy `ace.py` standalone file
- Now uses modular package architecture exclusively
- No `use_new_architecture` config needed (always uses modular)

### ✨ New Modular Architecture

Refactored from single 4642-line file into 18 modular files:

**Protocol Layer** (isolated, reusable):
- `protocol/constants.py` - Protocol constants
- `protocol/packet.py` - Packet encoding/decoding, CRC

**Device Layer** (hardware abstraction):
- `device/ace_device.py` - Pure hardware driver (550 lines)
- `device/device_manager.py` - Multi-device pool management
- `device/device_discovery.py` - USB auto-detection
- `device/device_mapper.py` - Persistent device tracking

**Sensors Layer**:
- `sensors/runout_helper.py` - Filament sensor management

**Commands Layer** (organized by category):
- `commands/tool_commands.py` - Tool changes, feed, retract
- `commands/config_commands.py` - Gate mapping, endless spool
- `commands/status_commands.py` - Status display with filtering

**Controller Layer**:
- `ace_controller.py` - Main orchestration (289 lines)

### 📊 Metrics

- **Files**: 1 monolithic → 18 modular files
- **Largest file**: 4642 lines → 550 lines (88% reduction)
- **Testable units**: 1 class → 11+ classes
- **Architecture**: Monolithic → Clean 3-layer + commands

### 🔧 Installation Changes

- `install.sh` now creates `ace/` package only
- No standalone `ace.py` in `klippy/extras/`
- All files symlinked to `~/klipper/klippy/extras/ace/`

### 📝 Configuration

Same configuration as before:

```ini
[ace]
serial: /dev/ttyACM0
# OR
auto_detect: True
```

No changes needed to existing configs (except remove `use_new_architecture` if present).

### 🚀 Features

All existing features maintained:
- Multi-device support (0-4 ACE devices)
- Auto-detection via USB
- Tool change orchestration
- Filament sensors
- Dryer control
- Gate configuration
- Endless spool

### 📚 Documentation

New documentation:
- `extras/ARCHITECTURE.md` - Detailed architecture guide
- `extras/REFACTORING_STATUS.md` - Refactoring progress
- `extras/README.md` - Quick start guide

### 🐛 Bug Fixes

- Fixed Klipper load conflict (single entry point)
- Clean module imports (no circular dependencies)

---

## [1.x.x] - Previous Versions

Previous versions used monolithic `ace.py` file.
