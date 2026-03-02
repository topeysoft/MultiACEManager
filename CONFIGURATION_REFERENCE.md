# KlipperACE Configuration Reference

Complete reference for all `[ace]` configuration parameters.

For quick start setup, see the [README](./README.md). For multi-ACE configuration methods, see the [Multi-ACE Setup section](./README.md#-multi-ace-setup).

---

## Required Parameters

You must provide **one** of the following to identify ACE devices:

```ini
[ace]
# Option A: List serial ports explicitly
serial_ports: /dev/ttyACM0, /dev/ttyACM1

# Option B: Auto-detect ACE devices via USB
auto_detect: true
```

You must also provide at least one sensor pin:

```ini
extruder_sensor_pin: ^EBBCan: PB9    # Required
```

---

## Connection

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `serial_ports` | string | — | Comma-separated list of ACE serial ports |
| `auto_detect` | bool | `false` | Auto-detect ACE devices via USB VID/PID |
| `baud` | int | `115200` | Serial baud rate |
| `connect_retry_delay` | float | `1.0` | Initial delay (seconds) between connection retries (exponential backoff) |
| `connect_retry_max` | int | `10` | Maximum connection retry attempts before giving up |

---

## Sensor Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `extruder_sensor_pin` | pin | — | **Required.** MCU pin for filament sensor at extruder. Used for runout detection and tool change sequencing |
| `toolhead_sensor_pin` | pin | — | Optional. MCU pin for sensor before the cutter/at toolhead. Enables dual-sensor mode for more precise loading |

**Single-sensor mode** (extruder only): Filament is fed from the ACE gate until the extruder sensor triggers, then pushed to the nozzle by distance.

**Dual-sensor mode** (extruder + toolhead): Filament feeds to extruder sensor, then to toolhead sensor, then to nozzle. More precise but requires two sensors.

---

## Speed Settings

| Parameter | Type | Default | Unit | Description |
|-----------|------|---------|------|-------------|
| `feed_speed` | int | `50` | mm/s | Speed for feeding filament from ACE toward extruder (range: 10-80) |
| `retract_speed` | int | `50` | mm/s | Speed for retracting filament back to ACE (range: 10-80) |
| `extruder_move_speed` | int | `10` | mm/s | Speed for extruder stepper movements during tool change |
| `toolhead_homing_speed` | int | `10` | mm/s | Speed when homing to the toolhead sensor |
| `sensor_clear_speed` | int | `20` | mm/s | Low speed for ACE pull while monitoring sensor during unload |

---

## Distance Settings

These distances must be tuned for your specific printer setup.

| Parameter | Type | Default | Unit | Description |
|-----------|------|---------|------|-------------|
| `toolchange_retract_length` | int | `100` | mm | Distance from splitter to extruder sensor. Full retract length during unload |
| `toolchange_feed_length` | int | `100` | mm | Total feed length from ACE gate to extruder sensor |
| `sensor_overshoot_compensation` | int | `0` | mm | Retract after extruder sensor triggers to compensate for momentum overshoot. 0 = disabled |
| `extruder_clearance_length` | int | `20` | mm | Distance the extruder retracts per retry when clearing the sensor during unload |
| `sensor_clear_max_distance` | int | `20` | mm | Maximum distance ACE pulls per retry when clearing the sensor |
| `toolhead_homing_max` | int | `100` | mm | Maximum distance to feed when searching for the toolhead sensor |
| `toolhead_sensor_to_nozzle` | int | `0` | mm | Distance from toolhead sensor to nozzle tip (dual-sensor mode) |
| `extruder_sensor_to_nozzle` | int | `0` | mm | Distance from extruder sensor to nozzle tip (single-sensor mode) |

---

## Temperature Management

KlipperACE can automatically pre-heat the extruder when switching to a gate with a different target temperature.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enable_temp_preheat` | bool | `true` | Auto-preheat extruder before tool change if target temp differs |
| `temp_preheat_threshold` | int | `20` | Temperature delta (in C) that triggers pre-heating. If current temp is within this margin of the target, preheat is skipped |
| `temp_stabilize_time` | float | `3.0` | Seconds to wait after reaching target temperature before proceeding |
| `max_dryer_temperature` | int | `55` | Maximum allowed dryer temperature (C). Commands requesting higher temps are capped to this value |

---

## Macro Hooks

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `poop_macros` | string | `_POOP` | Macro name called after filament load to prime/purge the nozzle |
| `cut_macros` | string | `_CUT_TIP` | Macro name called before filament unload to cut the tip |
| `error_macros` | string | — | Optional macro called on feed errors. Receives `TOOL=` and `ERROR=` parameters |

Your macros should be defined in your `ace.cfg` or `printer.cfg`. Example:

```ini
[gcode_macro _POOP]
gcode:
    G92 E0
    G1 E30 F300
    G92 E0

[gcode_macro _CUT_TIP]
gcode:
    G92 E0
    G1 E-3 F3600
    G92 E0
```

---

## Behavior

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `auto_register_t_macros` | bool | `false` | Automatically generate `T0`, `T1`, ... `TN` macros that call `ACE_CHANGE_TOOL`. Set to `true` if you don't define your own T macros |
| `log_level` | string | `INFO` | Logging verbosity: `ERROR`, `INFO`, or `DEBUG` |

---

## Device Manager (Performance Tuning)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `adaptive_polling` | bool | `true` | Adjusts polling frequency based on device activity (0.2s when active, up to 30s when idle). Reduces CPU usage |
| `poll_interval` | float | `2.0` | Fixed polling interval in seconds. Only used when `adaptive_polling` is `false` |

---

## Example: Minimal Config

```ini
[ace]
auto_detect: true
extruder_sensor_pin: ^EBBCan: PB9
toolchange_retract_length: 650
poop_macros: _POOP
cut_macros: _CUT_TIP
```

## Example: Full Config

```ini
[ace]
# Device detection
serial_ports: /dev/ttyACM0, /dev/ttyACM1
baud: 115200
connect_retry_delay: 1.0
connect_retry_max: 10

# Sensors
extruder_sensor_pin: ^EBBCan: PB9
toolhead_sensor_pin: ^EBBCan: PB8

# Speeds (mm/s)
feed_speed: 50
retract_speed: 50
extruder_move_speed: 10
toolhead_homing_speed: 10
sensor_clear_speed: 20

# Distances (mm) - tune for your setup
toolchange_retract_length: 650
toolchange_feed_length: 650
sensor_overshoot_compensation: 0
extruder_clearance_length: 20
sensor_clear_max_distance: 20
toolhead_homing_max: 100
toolhead_sensor_to_nozzle: 20
extruder_sensor_to_nozzle: 0

# Temperature
enable_temp_preheat: true
temp_preheat_threshold: 20
temp_stabilize_time: 3.0
max_dryer_temperature: 55

# Macros
poop_macros: _POOP
cut_macros: _CUT_TIP
error_macros: _ACE_ERROR_HANDLER

# Behavior
auto_register_t_macros: false
log_level: INFO
adaptive_polling: true
```
