# KlipperACE Feed Recovery Guide

When filament feeding fails during a tool change, KlipperACE pauses the print and gives you options to recover without losing the job.

---

## How Feed Timeout Works

During a tool change, KlipperACE feeds filament from the ACE gate toward the toolhead sensor (or extruder sensor in single-sensor mode). If the sensor doesn't trigger within the expected distance, a **feed timeout** occurs:

1. Filament movement stops immediately
2. The print is **paused**
3. A diagnostic message appears in the console with the tool number and distance fed
4. Recovery commands become available

---

## Recovery Commands

### ACE_RETRY_FEED

Retry the feed operation after clearing the obstruction.

```gcode
ACE_RETRY_FEED
```

**Workflow:**
1. Identify and clear the obstruction (see Diagnostic Tips below)
2. Run `ACE_RETRY_FEED` in the Klipper console
3. KlipperACE retries the feed from where it left off
4. If successful, the tool change completes and the print resumes

You get up to **3 total attempts** (the initial attempt + 2 retries). If all attempts fail, the print is canceled.

### ACE_CANCEL_FEED

Abort the tool change and cancel the print.

```gcode
ACE_CANCEL_FEED
```

Use this when:
- The obstruction cannot be cleared in place
- You need to physically access the filament path
- You want to restart the print from scratch

---

## Diagnostic Tips

When a feed timeout occurs, check these common causes:

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Filament visible but not moving | Filament jam or tangle at spool | Untangle or trim filament, then `ACE_RETRY_FEED` |
| Grinding sounds from extruder | Extruder skipping steps | Check extruder tension and gear condition |
| No filament at extruder entry | Filament broke in bowden tube | Remove broken piece, reload gate, retry |
| Sensor light on but timeout | Debris blocking sensor | Clean sensor with compressed air |
| Short distance fed before timeout | Bowden tube disconnected or kinked | Check all tube fittings |

**Useful diagnostic commands:**
- `ACE_GET_STATUS VERBOSE=1` — check gate states and sensor readings
- `ACE_LIST_DEVICES` — verify device connectivity
- `QUERY_FILAMENT_SENSOR SENSOR=extruder_sensor` — check sensor state directly

---

## Error Macro (Optional)

You can configure a custom macro that runs automatically when a feed error occurs:

```ini
[ace]
error_macros: _ACE_ERROR_HANDLER
```

```ini
[gcode_macro _ACE_ERROR_HANDLER]
gcode:
    {% set tool = params.TOOL|default(-1)|int %}
    {% set error = params.ERROR|default("unknown") %}
    M117 ACE Error: Tool {tool} - {error}
    # Add custom actions: LED color, beep, notification, etc.
```

---

## Related Configuration

These parameters affect feed behavior and timeout thresholds. See [CONFIGURATION_REFERENCE.md](./CONFIGURATION_REFERENCE.md) for details.

| Parameter | Default | Effect |
|-----------|---------|--------|
| `feed_speed` | 50 mm/s | Faster feed = less time to timeout, but may miss sensor |
| `toolchange_feed_length` | 100 mm | Maximum feed distance before timeout |
| `toolhead_homing_max` | 100 mm | Maximum distance when searching for toolhead sensor |
| `sensor_overshoot_compensation` | 0 mm | Retract after sensor triggers to compensate for momentum |
