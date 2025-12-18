# ACE Pro API Discovery Guide

This document outlines methods for discovering undocumented functionality in the Anycubic ACE Pro, including potential jam detection and filament monitoring features.

## Table of Contents
- [Current Known API Methods](#current-known-api-methods)
- [Protocol Overview](#protocol-overview)
- [Discovery Methods](#discovery-methods)
- [Potential Jam Detection](#potential-jam-detection)
- [Using the Diagnostic Tools](#using-the-diagnostic-tools)
- [Analysis Checklist](#analysis-checklist)

---

## Current Known API Methods

### From KlipperACE Implementation

Based on analysis of `ace.py` and `AFC_ACE_protocol.py`:

#### Device Information
- **`get_info`** - Returns model, firmware version
  ```json
  Response: {
    "id": <request_id>,
    "result": {
      "model": "ACE Pro",
      "firmware": "<version>"
    }
  }
  ```

- **`get_status`** - Returns comprehensive device state (polled every 0.5s)
  ```json
  Response: {
    "id": <request_id>,
    "result": {
      "status": "ready|busy",
      "temp": <temperature>,
      "enable_rfid": 0|1,
      "fan_speed": <rpm>,
      "feed_assist_count": <count>,
      "cont_assist_time": <seconds>,
      "dryer_status": {
        "status": "stop|running",
        "target_temp": <celsius>,
        "duration": <minutes>,
        "remain_time": <minutes>
      },
      "slots": [
        {
          "index": 0-3,
          "status": "empty|ready|loading|error|jammed?|blocked?",
          "sku": "<rfid_sku>",
          "type": "<material_type>",
          "color": [R, G, B]
        },
        ...
      ]
    }
  }
  ```

#### Filament Operations
- **`feed_filament`** / **`feed`** - Feed filament forward
  - Parameters: `{"index": 0-3, "length": <mm>, "speed": 10-80}`
  - Alternative parameter name: `"len"` instead of `"length"`

- **`unwind_filament`** / **`back`** - Retract filament
  - Parameters: `{"index": 0-3, "length": <mm>, "speed": 10-80}`
  - Alternative parameter name: `"len"` instead of `"length"`

- **`update_feeding_speed`** - Change speed during feed
  - Parameters: `{"index": 0-3, "speed": 10-80}`

- **`stop_feed_filament`** - Emergency stop
  - Parameters: `{"index": 0-3}`

- **`start_feed_assist`** / **`feed_assist`** - Enable continuous feeding mode
  - Parameters: `{"index": 0-3}`

- **`stop_feed_assist`** / **`feed_assist_off`** - Disable feed assist
  - Parameters: `{"index": 0-3}` or no parameters

#### Dryer Control
- **`drying`** / **`dryer_start`** - Start dryer
  - Parameters: `{"temp": <celsius>, "fan_speed": 7000, "duration": <minutes>}`
  - Alternative parameters: `"time"` instead of `"duration"`

- **`drying_stop`** / **`dryer_stop`** - Stop dryer
  - No parameters

---

## Protocol Overview

### Packet Structure
```
[0xFF 0xAA] [LEN:2] [JSON_PAYLOAD] [CRC16:2] [0xFE]
```

- **Header**: `0xFF 0xAA` (2 bytes)
- **Length**: Payload length in bytes, little-endian (2 bytes)
- **Payload**: JSON-encoded request/response (UTF-8)
- **CRC**: CRC16 of payload (2 bytes)
- **Tail**: `0xFE` (1 byte)

### CRC16 Calculation
```python
def calc_crc(buffer):
    _crc = 0xFFFF
    for byte in buffer:
        data = byte
        data ^= _crc & 0xff
        data ^= (data & 0x0f) << 4
        _crc = ((data << 8) | (_crc >> 8)) ^ (data >> 4) ^ (data << 3)
    return _crc
```

### Request Format
```json
{
  "id": <incrementing_number>,
  "method": "<method_name>",
  "params": {<optional_parameters>}
}
```

### Response Format
```json
{
  "id": <matching_request_id>,
  "result": {<method_results>},
  "msg": "success|<error_message>",
  "code": 0  // 0 = success, non-zero = error
}
```

---

## Discovery Methods

### 1. Using ACE_DEBUG Command

The `ACE_DEBUG` command allows testing arbitrary methods:

```gcode
ACE_DEBUG METHOD=<method_name> PARAMS='{"key": "value"}'
```

Example:
```gcode
ACE_DEBUG METHOD=get_diagnostics PARAMS='{}'
ACE_DEBUG METHOD=get_jam_status PARAMS='{"index": 0}'
```

### 2. Enable Debug Logging

Enable verbose protocol logging to see all responses:

```gcode
ACE_ENABLE_DEBUG
# Perform operations...
ACE_DISABLE_DEBUG
```

This logs all JSON-RPC responses to `klippy.log` with full field visibility.

### 3. Systematic Method Probing

Use the provided diagnostic macro:

```gcode
ACE_PROBE_METHODS
```

This tests common method naming patterns:
- `get_*` methods (diagnostics, errors, sensors, etc.)
- `set_*` methods
- `enable_*` / `disable_*` methods
- `clear_*` / `reset_*` methods

### 4. Monitor Feed Assist Metrics

The `feed_assist_count` and `cont_assist_time` fields may track motor load:

```gcode
ACE_MONITOR_FEED_ASSIST INDEX=0
```

High values could indicate:
- Increased friction (potential jam)
- Motor struggling
- Filament resistance

### 5. Analyze Slot Status Values

Known status values:
- `"empty"` - No filament detected
- `"ready"` - Filament loaded and ready
- `"loading"` - Actively feeding (unconfirmed)

Potential undocumented values:
- `"error"` - Generic error
- `"jammed"` - Jam detected
- `"blocked"` - Blockage detected
- `"unloading"` - Retracting
- `"fault"` - Hardware fault

### 6. Test Error Conditions

Deliberately trigger errors to discover error reporting:

1. **Feed from empty slot**:
   ```gcode
   ACE_FEED INDEX=<empty_slot> LENGTH=50
   ```

2. **Create resistance** (manually hold filament):
   ```gcode
   ACE_MONITOR_JAM_INDICATORS INDEX=0 LENGTH=50
   ```

3. **Check error response**:
   - Look for `"code": <non-zero>`
   - Check `"msg"` field
   - Monitor slot `"status"` changes

### 7. Serial Traffic Capture

For advanced reverse engineering:

```bash
# Monitor serial port with strace
strace -e read,write -s 1024 -p <klipper_pid> 2>&1 | grep '/dev/ttyACM0'

# Or use a USB analyzer
# Compare traffic from official ACE software vs. KlipperACE
```

---

## Potential Jam Detection

### Indicators to Monitor

1. **feed_assist_count**
   - Counter that may increment with motor effort
   - High values = filament resistance
   - Location: `get_status` response

2. **cont_assist_time**
   - Time spent in continuous feed assist
   - Long duration = potential jam
   - Location: `get_status` response

3. **Slot Status Changes**
   - Watch for transitions to `"error"`, `"jammed"`, or `"blocked"`
   - May occur during failed feed operations

4. **Feed Timeout**
   - If feed operation doesn't complete in expected time
   - Currently implemented in ace.py:752-758

5. **Error Codes**
   - Non-zero `"code"` in response
   - Check `"msg"` for descriptions

6. **Motor Current** (if exposed)
   - Potential undocumented field: `motor_current`
   - High current = motor struggling

7. **Encoder Data** (if available)
   - Potential fields: `encoder_position`, `encoder_delta`
   - Mismatch between commanded and actual movement

### Testing Jam Detection

```gcode
# 1. Get baseline metrics
ACE_FULL_STATUS_DUMP

# 2. Create controlled resistance (hold filament gently)
ACE_MONITOR_JAM_INDICATORS INDEX=0 LENGTH=100

# 3. Compare before/after metrics
ACE_FULL_STATUS_DUMP

# 4. Look for changes in:
#    - feed_assist_count
#    - cont_assist_time
#    - slot status
#    - any error codes
```

---

## Using the Diagnostic Tools

### Quick Start

1. **Include the diagnostics config**:
   ```ini
   [include ace_diagnostics.cfg]
   ```

2. **Get help**:
   ```gcode
   ACE_HELP_DISCOVERY
   ```

3. **Export current state**:
   ```gcode
   ACE_EXPORT_FULL_STATE
   ```

### Available Macros

| Macro | Purpose |
|-------|---------|
| `ACE_TEST_METHOD` | Test specific API method |
| `ACE_PROBE_METHODS` | Systematically test method names |
| `ACE_FULL_STATUS_DUMP` | Dump all status fields |
| `ACE_DISCOVER_SLOTS` | Analyze slot data fields |
| `ACE_MONITOR_FEED_ASSIST` | Track feed assist metrics |
| `ACE_MONITOR_JAM_INDICATORS` | Monitor for jam signals during feed |
| `ACE_EXPORT_FULL_STATE` | Complete device state export |
| `ACE_TEST_RFID_FEATURES` | Test RFID-related methods |
| `ACE_TEST_MAINTENANCE_METHODS` | Test maintenance APIs |
| `ACE_TEST_ERROR_CONDITIONS` | Analyze error reporting |
| `ACE_HELP_DISCOVERY` | Show usage help |

### Enhanced Logging Commands

```gcode
# Enable debug mode - logs all protocol responses
ACE_ENABLE_DEBUG

# Perform operations, check klippy.log for details
ACE_FEED INDEX=0 LENGTH=50

# Disable debug mode
ACE_DISABLE_DEBUG
```

---

## Analysis Checklist

### Step 1: Baseline Discovery
- [ ] Run `ACE_EXPORT_FULL_STATE` and save output
- [ ] Document all fields in `get_status` response
- [ ] Note any unknown fields or values

### Step 2: Method Discovery
- [ ] Run `ACE_PROBE_METHODS` (takes ~30 seconds)
- [ ] Check console for successful responses
- [ ] Document any new working methods

### Step 3: RFID Analysis (if applicable)
- [ ] Run `ACE_TEST_RFID_FEATURES`
- [ ] Note which methods succeed
- [ ] Check if RFID exposes additional data

### Step 4: Error Testing
- [ ] Test feed from empty slot
- [ ] Create manual resistance during feed
- [ ] Disconnect filament mid-operation
- [ ] Document error codes and messages

### Step 5: Feed Monitoring
- [ ] Run `ACE_MONITOR_JAM_INDICATORS` with normal feed
- [ ] Run again with manual resistance
- [ ] Compare `feed_assist_count` and `cont_assist_time`
- [ ] Note any patterns

### Step 6: Slot Status Mapping
- [ ] Document all observed status values
- [ ] Trigger each status deliberately if possible
- [ ] Map status to real-world conditions

---

## Suggested Methods to Test

### High Priority (likely to exist)
```
get_capabilities
get_diagnostics
get_errors
get_error_log
get_sensor_data
get_motor_status
clear_errors
```

### Medium Priority (reasonable to expect)
```
get_jam_status
get_blockage_status
get_load_status
get_statistics
get_maintenance
get_config
get_all_slots
```

### Low Priority (speculative)
```
get_tension
get_encoder_position
reset_jam_detection
calibrate
self_test
factory_reset
```

---

## Contributing Discoveries

If you discover new methods or fields:

1. Document the method name and parameters
2. Capture example request/response
3. Note when it's useful (e.g., jam detection, maintenance)
4. Test for side effects
5. Share findings with the community

### Example Documentation Format

```markdown
### get_diagnostics

**Purpose**: Returns diagnostic information about ACE hardware

**Request**:
```json
{
  "id": 123,
  "method": "get_diagnostics",
  "params": {}
}
```

**Response**:
```json
{
  "id": 123,
  "result": {
    "motor_hours": 123.5,
    "feed_count": 1234,
    "jam_count": 5,
    "last_error": "none"
  },
  "msg": "success",
  "code": 0
}
```

**Usage**:
```gcode
ACE_DEBUG METHOD=get_diagnostics PARAMS='{}'
```

**Notes**: Useful for tracking device wear and jam history
```

---

## Additional Resources

### Firmware Analysis

Community reverse engineering efforts:
- GitHub: `printers-for-people/ACEResearch`
- Discussion: `Bushmills/Anycubic-Kobra-3-rooted/discussions/2`

### Related Projects

- **BunnyACE**: Original Klipper implementation by BlackFrogKok
- **ValgACE**: Alternative driver by agrloki
- **ACEPROSV08**: Sovol SV08 adaptation by szkrisz

---

## Safety Notes

⚠️ **Warning**: Some methods may affect device calibration or settings

- Avoid `factory_reset`, `calibrate`, `write_rfid` without understanding
- Test unknown methods with empty gates first
- Back up your ACE configuration before experimenting
- Monitor for unusual behavior (grinding, overheating)

---

## Revision History

- **2025-01-18**: Initial discovery guide created
  - Documented known API methods from KlipperACE
  - Created diagnostic macros for method discovery
  - Added enhanced logging to ace.py
  - Compiled analysis checklist and testing procedures

---

## Summary

The ACE Pro likely has undocumented features for:

1. **Jam Detection**: Via `feed_assist_count`, `cont_assist_time`, or dedicated methods
2. **Error Logging**: Potential `get_errors` or `get_error_log` methods
3. **Diagnostics**: Usage statistics, motor hours, maintenance data
4. **Advanced Sensors**: Motor current, encoder position, tension monitoring

Use the provided diagnostic tools to systematically discover these features. Start with `ACE_PROBE_METHODS` and `ACE_MONITOR_JAM_INDICATORS`, then analyze the responses for previously undocumented data.

Good luck with your discoveries! 🔍
