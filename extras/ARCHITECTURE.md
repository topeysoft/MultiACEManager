# ACE Pro System Architecture

## Overview

The ACE Pro system has been refactored from a monolithic 4642-line file into a clean, modular architecture with 18 well-organized files.

## Directory Structure

```
KlipperACE/extras/
├── __init__.py                    # Package entry, feature flag support
├── exceptions.py                  # Custom exceptions
├── ace_controller.py              # Main orchestration layer (289 lines)
├── MIGRATION_GUIDE.md             # User migration documentation
├── REFACTORING_STATUS.md          # Refactoring progress tracking
├── ARCHITECTURE.md                # This file
│
├── protocol/                      # Protocol layer (isolated, reusable)
│   ├── __init__.py
│   ├── constants.py               # Protocol constants, timeouts
│   └── packet.py                  # Packet encoding/decoding, CRC
│
├── device/                        # Hardware abstraction layer
│   ├── __init__.py
│   ├── ace_device.py              # Pure hardware driver (550 lines)
│   ├── device_manager.py          # Multi-device pool management (350 lines)
│   ├── device_discovery.py        # USB auto-detection (250 lines)
│   └── device_mapper.py           # Persistent device tracking (150 lines)
│
├── sensors/                       # Sensor management
│   ├── __init__.py
│   └── runout_helper.py           # Filament sensor logic (200 lines)
│
└── commands/                      # G-code command handlers (by category)
    ├── __init__.py
    ├── tool_commands.py           # Tool changes, feed, retract (192 lines)
    ├── config_commands.py         # Gate mapping, endless spool (140 lines)
    └── status_commands.py         # Status display, diagnostics (151 lines)
```

## Architectural Layers

### Layer 1: Protocol (Foundation)

**Purpose**: Low-level protocol handling, no dependencies

**Components**:
- `protocol/constants.py` - All protocol constants (headers, timeouts, gates per device)
- `protocol/packet.py` - Packet encoding/decoding, CRC16 calculation

**Key Features**:
- Zero dependencies (pure Python)
- Fully unit testable
- Reusable in other projects
- Protocol versioning support

### Layer 2: Hardware (Device Abstraction)

**Purpose**: Device communication and management

**Components**:
- `device/ace_device.py` - Pure hardware driver for single ACE device
  - Serial communication
  - Request/response handling
  - Simple commands (feed, retract, dryer, etc.)
  - No business logic

- `device/device_manager.py` - Multi-device pool management
  - Manages 0-4 ACE devices
  - Gate routing (global gate → device + local gate)
  - Connection lifecycle
  - Aggregated status

- `device/device_discovery.py` - USB device discovery
  - VID/PID matching (0x28E9:0x018A)
  - USB location tracking
  - Device enumeration

- `device/device_mapper.py` - Persistent device properties
  - Device ID mapping
  - Property storage (per device)
  - Last seen tracking

**Key Features**:
- Device independence (each device is isolated)
- Hot-plug support (via discovery)
- Stable device IDs (based on USB location)
- No Klipper dependencies in core driver

### Layer 3: Sensors (Shared Resources)

**Purpose**: Filament sensor management shared across all devices

**Components**:
- `sensors/runout_helper.py` - MmuRunoutHelper class
  - Extruder sensor handling
  - Toolhead sensor handling
  - Runout detection
  - Insert/remove events

**Key Features**:
- Shared across all ACE devices
- Event-driven architecture
- Button feedback support
- Runout detection during prints

### Layer 4: Commands (User Interface)

**Purpose**: G-code command handlers organized by category

**Components**:
- `commands/tool_commands.py` - Tool operations
  - `ACE_CHANGE_TOOL` - Change to tool (with unload/load sequences)
  - `ACE_FEED` - Feed filament from gate
  - `ACE_RETRACT` - Retract filament to gate

- `commands/config_commands.py` - Configuration
  - `ACE_GATE_MAP` - Configure gate properties (color, material, temp)
  - `ACE_ENDLESS_SPOOL` - Enable/disable endless spool

- `commands/status_commands.py` - Diagnostics
  - `ACE_GET_STATUS` - System status (with verbose/device filtering)

**Key Features**:
- Organized by category (tool, config, status)
- Easy to extend (add new commands without touching core)
- Clean separation from business logic
- Comprehensive parameter validation

### Layer 5: Controller (Orchestration)

**Purpose**: Main business logic and coordination

**Component**:
- `ace_controller.py` - AceController class (289 lines)
  - Tool change orchestration
  - Sensor lifecycle management
  - Command module coordination
  - Save variables integration
  - Klipper event handling

**Key Features**:
- Delegates to command modules (not monolithic)
- Coordinates device manager
- Manages shared sensors
- Handles Klipper lifecycle (ready, disconnect)
- Persistent state (via save_variables)

## Data Flow

### Tool Change Flow
```
User: ACE_CHANGE_TOOL TOOL=5
    ↓
commands/tool_commands.py:cmd_ACE_CHANGE_TOOL()
    ↓
ace_controller.py (validates, orchestrates)
    ↓
device/device_manager.py:get_device_for_gate(5)
    → Returns: (device_1, local_gate=1)  # 5 = device_1 (gates 4-7), local gate 1
    ↓
device/ace_device.py:feed() / retract()
    ↓
protocol/packet.py:encode()
    ↓
Serial communication to hardware
    ↓
protocol/packet.py:decode()
    ↓
Callback to command handler
    ↓
User feedback via gcode.respond_info()
```

### Multi-Device Gate Routing
```
Total Gates: 16 (4 devices × 4 gates each)

Global Gate → Device Mapping:
Gate 0-3   → Device 0 (local gates 0-3)
Gate 4-7   → Device 1 (local gates 0-3)
Gate 8-11  → Device 2 (local gates 0-3)
Gate 12-15 → Device 3 (local gates 0-3)

Routing Logic (device_manager.py):
  device_index = global_gate // 4
  local_gate = global_gate % 4
```

## Key Design Decisions

### 1. Feature Flag Migration

Users opt-in to new architecture via config:
```ini
[ace]
use_new_architecture: True
```

Default behavior uses legacy `ace.py` for 100% backward compatibility.

### 2. Command Module Pattern

Commands are organized into classes that:
- Take `controller` in `__init__`
- Implement `register()` method
- Access controller state via `self.controller`

This allows:
- Clean separation of concerns
- Easy testing (mock controller)
- Simple extension (new command modules)

### 3. Device Independence

Each `AceDevice` is fully independent:
- Own serial connection
- Own request/response queue
- Own status tracking
- No shared state

This enables:
- Concurrent operation
- Hot-plug support
- Device failure isolation

### 4. Protocol Abstraction

Protocol layer has zero dependencies:
- Pure Python
- No Klipper imports
- No device knowledge
- 100% unit testable

This enables:
- Reuse in other projects
- Easy protocol updates
- Independent testing

## Testing Strategy

### Unit Testing Hierarchy

1. **Protocol Layer** (no dependencies)
   - Test packet encoding/decoding
   - Test CRC calculation
   - Test packet validation

2. **Device Layer** (mock serial)
   - Test device discovery
   - Test device mapping
   - Test AceDevice commands

3. **Sensor Layer** (mock pins)
   - Test sensor events
   - Test runout detection

4. **Command Layer** (mock controller)
   - Test command parsing
   - Test validation
   - Test error handling

5. **Controller Layer** (integration)
   - Test with mock devices
   - Test tool change flow
   - Test status aggregation

## Benefits Summary

### For Users
- **Zero-risk migration** - Feature flag opt-in
- **Multi-device support** - Auto-detection, stable IDs
- **Better diagnostics** - Verbose status, per-device filtering
- **Hot-plug ready** - Add/remove devices without config changes

### For Developers
- **Modularity** - 18 files vs 1 monolithic file
- **Testability** - 11+ independent testable classes
- **Maintainability** - Largest file: 550 lines (was 4642)
- **Extensibility** - Add features without touching core

### Metrics

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Files | 1 | 18 | 18× more modular |
| Largest file | 4642 lines | 550 lines | 88% reduction |
| Testable units | 1 class | 11+ classes | 11× more testable |
| Layer separation | None | 4 layers | Clean architecture |
| Command organization | Monolithic | 3 modules | By category |

## Future Enhancements

### Phase 6: Complete Implementation
- Full tool change sequence (unload/load with sensors)
- Endless spool logic (material matching)
- Hot-plug event handling
- Dryer commands

### Phase 7: Advanced Features
- Device health monitoring
- Performance metrics
- Advanced diagnostics
- USB-over-network support

### Phase 8: Stabilization
- Extensive hardware testing
- Performance optimization
- Make new architecture default
- Deprecate legacy ace.py

## Migration Path

### Current State
- Legacy `ace.py` (default)
- New architecture (opt-in via feature flag)
- 100% backward compatible

### Target State (v3.0)
- New architecture (default)
- Legacy deprecated
- Removal of ace.py

### Migration Timeline
- **v2.0** - New architecture available, opt-in
- **v2.1** - Complete TODO implementations
- **v2.5** - New architecture becomes default (with fallback)
- **v3.0** - Remove legacy, new architecture only

---

*Last Updated: 2025-11-29*
*Architecture Version: 2.0.0*
