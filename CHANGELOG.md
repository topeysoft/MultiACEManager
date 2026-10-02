# Changelog

## Unreleased

- `ACE_CHANGE_TOOL ... PURGE=0` loads without running the purge (poop) macro, for a spool the
  same colour as the one it replaces. Default `PURGE=1` keeps the old behaviour.
- Hot-plug: a unit that was off, still starting, or flapping when Klipper started is picked up
  once it has stayed on USB for 15 s, without a restart. With no filament loaded it gets the
  order a restart would give (config `device_order`, then remembered offsets); with filament
  loaded, existing gates stay put and the new unit goes after them. Never during a print.
  A unit whose driver gave up retrying reconnects when its port is back and steady.
- Fix "Could not exclusively lock port" churn: after a read error the write step ran on the
  closed port and scheduled a second reconnect; the second open failed on the lock and dropped
  the good connection. One connect attempt at a time now, and stale attempts are ignored.
- Gate order is now remembered: devices keep their gate range across restarts and re-cabling as
  long as they stay on the same USB port; new units are appended instead of re-rolling existing gates.
- New `ACE_SET_DEVICE_ORDER DEVICES=...` command and optional `device_order:` config option.
- Fix packet framing: a 0xFE byte in the CRC/length no longer truncates responses.
- Fix `stop_feed_assist` raising TypeError on an invalid gate.
- Plugin errors inside G-code handlers (feed timeouts, sensor not clearing) are now reported as
  normal command errors instead of shutting Klipper down with "Internal error".
- Device status entries include `alias`.
- Unload: the ACE now pulls *while* the extruder retracts (started first, same speed, plus a slack
  take-up pull). The previous extruder-then-ACE sequence let filament buckle into the hub, the
  extruder gears ground, and the extruder sensor never cleared.
- Add offline test suite and `dev.sh` development loop.

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
