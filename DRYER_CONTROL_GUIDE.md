# ACE Multi-Device Dryer Control Guide

## Overview

Each ACE Pro device has its own **independent dryer** that can be controlled separately. This guide explains how to use the per-device dryer control system in both backend API and UI.

---

## Key Features

### ✅ Independent Control
- Each ACE device has its own dryer
- Control each dryer independently by device ID or gate number
- Start/stop dryers without affecting other devices

### ✅ Real-Time Status
- View all dryers at once with `ACE_GET_DRYER_STATUS`
- Each dryer reports: status, current temp, target temp, time remaining
- Dryer status shown in `ACE_SHOW_USB_INFO` diagnostic

### ✅ Simple Macro-Based UI
- Pre-configured macros for each device (`ACE1_START_DRYER`, `ACE2_START_DRYER`)
- Temperature presets for common materials (PLA, PETG, ABS, Nylon, TPU)
- One-click stop-all functionality

### ✅ Moonraker API Integration
- Full dryer status exposed in Moonraker API
- UI frameworks (Mainsail/Fluidd) can display all dryers
- Per-device dryer status in `printer.ace_manager.dryers` array

---

## Backend API

### G-code Commands

#### ACE_START_DRYING
Start the dryer on a specific ACE device.

**Usage**:
```gcode
# By device ID (USB location)
ACE_START_DRYING DEVICE=hub_1_port_1 TEMP=60 DURATION=240

# By gate number (convenience)
ACE_START_DRYING GATE=0 TEMP=60 DURATION=240
ACE_START_DRYING GATE=4 TEMP=55 DURATION=180
```

**Parameters**:
- `DEVICE=<device_id>` - Device ID (e.g., `hub_1_port_1`)
- `GATE=<gate_num>` - Gate number (0-15) - system finds the correct device
- `TEMP=<temperature>` - Target temperature in °C (required)
- `DURATION=<minutes>` - Drying duration in minutes (default: 240)

**Examples**:
```gcode
# Start first device's dryer at 60°C for 4 hours
ACE_START_DRYING GATE=0 TEMP=60 DURATION=240

# Start second device's dryer at 55°C for 3 hours
ACE_START_DRYING GATE=4 TEMP=55 DURATION=180

# By explicit device ID
ACE_START_DRYING DEVICE=hub_1_port_2 TEMP=65 DURATION=360
```

#### ACE_STOP_DRYING
Stop the dryer on a specific ACE device.

**Usage**:
```gcode
# By device ID
ACE_STOP_DRYING DEVICE=hub_1_port_1

# By gate number
ACE_STOP_DRYING GATE=0
ACE_STOP_DRYING GATE=4
```

**Parameters**:
- `DEVICE=<device_id>` - Device ID
- `GATE=<gate_num>` - Gate number

#### ACE_GET_DRYER_STATUS
Display status of all dryers.

**Usage**:
```gcode
ACE_GET_DRYER_STATUS
```

**Output Example**:
```
======================================================================
ACE Dryer Status
======================================================================

ACE Unit 1 (hub_1_port_1) - Gates 0-3:
  Status:    🔥 Running
  Current:   55°C
  Target:    60°C
  Duration:  240 minutes
  Remaining: 180 minutes

ACE Unit 2 (hub_1_port_2) - Gates 4-7:
  Status:    ⭘ Stopped
  Current:   25°C

======================================================================
Commands:
  ACE_START_DRYING DEVICE=<id> TEMP=<temp> DURATION=<min>
  ACE_START_DRYING GATE=<num> TEMP=<temp> DURATION=<min>
  ACE_STOP_DRYING DEVICE=<id>  or  ACE_STOP_DRYING GATE=<num>
======================================================================
```

---

## Moonraker API Response

### Query
```http
GET /printer/objects/query?ace_manager
```

### Response Structure
```json
{
  "ace_manager": {
    "status": "ready",
    "num_gates": 8,
    "num_devices": 2,

    "dryers": [
      {
        "device_id": "hub_1_port_1",
        "device_name": "ACE Unit 1",
        "gate_offset": 0,
        "status": "running",
        "temp": 55,
        "target_temp": 60,
        "duration": 240,
        "remain_time": 180
      },
      {
        "device_id": "hub_1_port_2",
        "device_name": "ACE Unit 2",
        "gate_offset": 4,
        "status": "stop",
        "temp": 25,
        "target_temp": 0,
        "duration": 0,
        "remain_time": 0
      }
    ],

    "devices_detail": [
      {
        "device_id": "hub_1_port_1",
        "gate_offset": 0,
        "dryer_status": {
          "status": "running",
          "target_temp": 60,
          "duration": 240,
          "remain_time": 180
        },
        "dryer_temp": 55,
        "gate_color": ["FFFFFF", "FF0000", "00FF00", "0000FF"],
        "gate_material": ["PLA", "PETG", "ABS", "TPU"],
        ...
      }
    ]
  }
}
```

### Fields Explained

**`dryers` Array** (NEW):
- One entry per ACE device
- Shows real-time dryer status for each device
- UI can display all dryers in a grid/list

**Per-Device Fields**:
- `device_id`: USB port-based device identifier
- `device_name`: Human-readable name (e.g., "ACE Unit 1")
- `gate_offset`: Starting gate number for this device
- `status`: "running" or "stop"
- `temp`: Current temperature
- `target_temp`: Target temperature (0 if stopped)
- `duration`: Total drying duration in minutes
- `remain_time`: Minutes remaining (0 if stopped)

---

## UI: Macro-Based Control

### Setup

1. **Include dryer macros** in your Klipper config:
```ini
[include ace_dryer_macros.cfg]
```

2. **Restart Klipper**:
```gcode
FIRMWARE_RESTART
```

### Usage in Mainsail/Fluidd

The macros will appear in the UI's macro panel:

#### Per-Device Control
- **ACE1_START_DRYER** - Start first device's dryer (default: 55°C, 4h)
- **ACE1_STOP_DRYER** - Stop first device's dryer
- **ACE2_START_DRYER** - Start second device's dryer
- **ACE2_STOP_DRYER** - Stop second device's dryer
- **ACE3_START_DRYER** / **ACE3_STOP_DRYER** (if 3+ devices)
- **ACE4_START_DRYER** / **ACE4_STOP_DRYER** (if 4 devices)

#### Temperature Presets
- **DRYER_PRESET_PLA** - 45°C for 2 hours
- **DRYER_PRESET_PETG** - 55°C for 4 hours
- **DRYER_PRESET_ABS** - 60°C for 4 hours
- **DRYER_PRESET_NYLON** - 65°C for 6 hours
- **DRYER_PRESET_TPU** - 50°C for 3 hours

#### Utility Macros
- **SHOW_DRYER_STATUS** - Display all dryer statuses
- **STOP_ALL_DRYERS** - Emergency stop for all dryers

### Examples

#### Start first device's dryer
```gcode
ACE1_START_DRYER TEMP=60 DURATION=240
```

#### Use preset on second device
```gcode
DRYER_PRESET_PETG GATE=4
```

#### Check all dryer statuses
```gcode
SHOW_DRYER_STATUS
```

#### Stop everything
```gcode
STOP_ALL_DRYERS
```

---

## Configuration

### Include Dryer Macros

Add to your `printer.cfg` or main configuration:

```ini
[include ace_dryer_macros.cfg]
```

### Customize Temperature Limits

Each ACE device has a `max_dryer_temperature` setting (default: 70°C):

```ini
[ace_manager]
auto_detect: true
max_dryer_temperature: 70  # Maximum allowed temperature
# ... other config
```

### Enable Auto-Detect

Make sure auto-detect is enabled to get per-device dryer control:

```ini
[ace_manager]
auto_detect: true  # Required for per-device control
# ... other config
```

---

## Diagnostics

### View USB Topology with Dryer Status

```gcode
ACE_SHOW_USB_INFO
```

**Output**:
```
======================================================================
ACE USB Port Mapping & Device Topology
======================================================================

Currently Connected Devices:
----------------------------------------------------------------------

✓ Device 1: hub_1_port_1
   ID Type:      USB Location
   USB Location: 1-1
   Serial Port:  /dev/ttyACM0
   Gate Range:   0-3
   Dryer:        🔥 Running (55°C → 60°C, 180min remaining)
   Materials:    [PLA, PETG, ABS, TPU]

✓ Device 2: hub_1_port_2
   ID Type:      USB Location
   USB Location: 1-2
   Serial Port:  /dev/ttyACM1
   Gate Range:   4-7
   Dryer:        ⭘ Stopped (25°C)
   Materials:    [ASA, Nylon, PC, FLEX]
```

### Check Specific Dryer Status

```gcode
ACE_GET_DRYER_STATUS
```

---

## Advanced: UI Integration

### Custom Mainsail/Fluidd Component

The `dryers` array can be used to build a custom UI component:

```javascript
// Fetch dryer status
const response = await fetch('/printer/objects/query?ace_manager');
const data = await response.json();
const dryers = data.result.status.ace_manager.dryers;

// Display each dryer
dryers.forEach(dryer => {
  console.log(`${dryer.device_name}: ${dryer.status}`);
  console.log(`  Temp: ${dryer.temp}°C / ${dryer.target_temp}°C`);
  console.log(`  Time: ${dryer.remain_time}min remaining`);
});
```

### Example UI Card

```html
<div class="ace-dryer-grid">
  <div v-for="dryer in dryers" :key="dryer.device_id" class="dryer-card">
    <h3>{{ dryer.device_name }}</h3>
    <div class="status" :class="dryer.status">
      {{ dryer.status === 'running' ? '🔥 Running' : '⭘ Stopped' }}
    </div>
    <div class="temperature">
      <span class="current">{{ dryer.temp }}°C</span>
      <span v-if="dryer.status === 'running'">
        → {{ dryer.target_temp }}°C
      </span>
    </div>
    <div v-if="dryer.status === 'running'" class="remaining">
      {{ dryer.remain_time }} min remaining
    </div>
    <button @click="startDryer(dryer.device_id)">Start</button>
    <button @click="stopDryer(dryer.device_id)">Stop</button>
  </div>
</div>
```

---

## Troubleshooting

### Q: Dryer commands return "Device not found"
**A:** Check device ID with `ACE_SHOW_USB_INFO` and use the exact ID shown.

### Q: Only one dryer shows in status
**A:** Make sure you're using the latest version with `dryers` array (not `dryer_status`).

### Q: Macros don't appear in UI
**A:**
1. Check that `ace_dryer_macros.cfg` is included in your config
2. Run `FIRMWARE_RESTART`
3. Verify no syntax errors in the macro file

### Q: Temperature limit error
**A:** Check `max_dryer_temperature` in your config. Default is 70°C. Adjust if needed.

### Q: Which device is ACE1 vs ACE2?
**A:** Run `ACE_SHOW_USB_INFO` to see the device order. Devices are numbered by USB port order.

---

## Best Practices

### 1. Label Your USB Ports
Physically label your USB hub ports so you know which device is which.

### 2. Use Presets for Common Materials
The temperature presets are calibrated for each material type. Use them for consistent results.

### 3. Check Status Before Starting
Run `ACE_GET_DRYER_STATUS` to see if any dryers are already running.

### 4. Monitor Temperature
Check dryer temperature occasionally to ensure it's reaching target temp.

### 5. Don't Exceed Max Temperature
Never exceed the `max_dryer_temperature` setting (default 70°C) to avoid damaging filament or hardware.

---

## Material Drying Guide

| Material | Temperature | Duration | Preset Macro |
|----------|-------------|----------|--------------|
| PLA      | 45°C        | 2 hours  | `DRYER_PRESET_PLA` |
| PETG     | 55°C        | 4 hours  | `DRYER_PRESET_PETG` |
| ABS/ASA  | 60°C        | 4 hours  | `DRYER_PRESET_ABS` |
| Nylon    | 65°C        | 6 hours  | `DRYER_PRESET_NYLON` |
| TPU/TPE  | 50°C        | 3 hours  | `DRYER_PRESET_TPU` |
| PC       | 65°C        | 6 hours  | Custom |

---

## Quick Reference

### Commands
```gcode
ACE_START_DRYING GATE=0 TEMP=60 DURATION=240
ACE_STOP_DRYING GATE=0
ACE_GET_DRYER_STATUS
ACE_SHOW_USB_INFO
```

### Macros
```gcode
ACE1_START_DRYER TEMP=60 DURATION=240
ACE1_STOP_DRYER
DRYER_PRESET_PETG GATE=0
SHOW_DRYER_STATUS
STOP_ALL_DRYERS
```

### API
```http
GET /printer/objects/query?ace_manager
```
Response: `dryers` array with per-device status

---

## Summary

✅ **Each ACE device has an independent dryer**
✅ **Control by device ID or gate number**
✅ **Simple macro-based UI**
✅ **Full Moonraker API integration**
✅ **Real-time status for all dryers**
✅ **Temperature presets for common materials**

For questions or issues, refer to the main [USB_PORT_MAPPING_GUIDE.md](USB_PORT_MAPPING_GUIDE.md) or run `ACE_SHOW_USB_INFO` for device diagnostics.
