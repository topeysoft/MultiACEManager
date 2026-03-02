# ACE Device Mapper Migration Guide

## Problem: Corrupted ace_vars.cfg

If you see this error:
```
configparser.DuplicateOptionError: While reading from '/home/pi/printer_data/config/ace_vars.cfg' [line 10]:
option 'ace_hub_1_port_1_3_4_3' in section 'Variables' already exists
```

This means your `ace_vars.cfg` file has duplicate entries from the old device property storage system.

---

## Quick Fix

### Option 1: Clean ace_vars.cfg (Recommended)

1. **Backup the corrupted file**:
```bash
cp ~/printer_data/config/ace_vars.cfg ~/printer_data/config/ace_vars.cfg.backup
```

2. **Edit the file** to remove duplicate and device-specific entries:
```bash
nano ~/printer_data/config/ace_vars.cfg
```

3. **Remove any lines** that start with `ace_hub_` or `ace_usb_` or have long device IDs
   - Keep only these variables:
     - `ace__revision`
     - `ace_current_index`
     - `ace_endless_spool`
     - `ace_filament_pos`
     - `ace_gate_color`
     - `ace_gate_type`
     - `ace_gate_temp`

4. **Example clean file**:
```ini
[Variables]
ace__revision = 1
ace_current_index = -1
ace_endless_spool = False
ace_filament_pos = 'spliter'
ace_gate_color = ['FFFFFF', 'FF0000', '00FF00', '0000FF']
ace_gate_type = ['PLA', 'PETG', 'ABS', 'TPU']
ace_gate_temp = [210, 230, 250, 230]
```

5. **Restart Klipper**:
```bash
sudo systemctl restart klipper
```

### Option 2: Start Fresh

1. **Backup and remove the corrupted file**:
```bash
cp ~/printer_data/config/ace_vars.cfg ~/printer_data/config/ace_vars.cfg.backup
rm ~/printer_data/config/ace_vars.cfg
```

2. **Copy the clean template**:
```bash
cp ~/klipper/extras/ace_vars.cfg ~/printer_data/config/ace_vars.cfg
```
*Note: Adjust path if your ace_vars.cfg template is elsewhere*

3. **Restart Klipper**:
```bash
sudo systemctl restart klipper
```

4. **Reconfigure your gates** using:
```gcode
ACE_GATE_MAP GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
ACE_GATE_MAP GATE=1 COLOR=00FF00 TYPE=PETG TEMP=230
# etc.
```

---

## What Changed?

### Old System (Broken)
- Device-specific properties stored in `ace_vars.cfg` with device ID keys
- Example: `ace_hub_1_port_1_3_4_3_gate_color = ['FFFFFF', ...]`
- **Problem**: Long keys with special characters caused duplicates and corruption

### New System (Fixed)
- Device-specific properties stored in `ace_device_map.cfg`
- `ace_vars.cfg` only stores global/runtime state
- Clean separation of concerns

### Storage Locations

**ace_vars.cfg** (Runtime state - shared across all devices):
- `ace_current_index` - Currently selected gate
- `ace_endless_spool` - Endless spool enabled/disabled
- `ace_filament_pos` - Current filament position
- `ace_gate_color`, `ace_gate_type`, `ace_gate_temp` - Default arrays

**ace_device_map.cfg** (Device properties - persistent per device):
- Device metadata (USB location, last seen, etc.)
- Per-device gate colors, materials, temperatures
- Properties follow the device when it moves ports

---

## Automatic Migration

The updated code automatically:
1. ✅ Stops writing device-specific keys to `ace_vars.cfg`
2. ✅ Stores device properties in `ace_device_map.cfg` instead
3. ✅ Migrates existing properties on first run
4. ✅ Reads from device mapper, not save_variables

---

## Verification

After fixing, verify the system works:

### 1. Check Files
```bash
# ace_vars.cfg should only have simple variables
cat ~/printer_data/config/ace_vars.cfg

# ace_device_map.cfg should have device-specific properties
cat ~/printer_data/config/ace_device_map.cfg
```

### 2. Test Device Mapping
```gcode
ACE_SHOW_USB_INFO
```

Expected output shows devices with properties:
```
✓ Device 1: hub_1_port_1
   Gate Range:   0-3
   Materials:    [PLA, PETG, ABS, TPU]
   Colors:       [FFFFFF, FF0000, 00FF00, 0000FF]
```

### 3. Test Gate Mapping
```gcode
ACE_GATE_MAP GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
```

This should:
- Update `ace_device_map.cfg` (not `ace_vars.cfg`)
- Show success message
- Persist across reboots

### 4. Test Property Persistence
1. Set gate properties:
```gcode
ACE_GATE_MAP GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
ACE_GATE_MAP GATE=4 COLOR=00FF00 TYPE=PETG TEMP=230
```

2. Check they're stored in device mapper:
```bash
cat ~/printer_data/config/ace_device_map.cfg
```

3. Reboot and verify properties persist:
```bash
sudo systemctl restart klipper
```

4. Check with:
```gcode
ACE_SHOW_USB_INFO
```

---

## Troubleshooting

### Q: Still getting "DuplicateOptionError" after cleaning ace_vars.cfg
**A:** Make sure you removed ALL lines with device IDs (lines starting with `ace_hub_` or `ace_usb_`). Only keep the simple variables listed above.

### Q: Properties don't persist after reboot
**A:** Check that `ace_device_map.cfg` exists and has the `[device:...]` sections:
```bash
cat ~/printer_data/config/ace_device_map.cfg
```

### Q: ACE_GATE_MAP doesn't save properties
**A:**
1. Check that device mapper is initialized (run `ACE_SHOW_USB_INFO`)
2. Verify auto_detect is enabled in your config
3. Check Klipper logs for errors

### Q: Lost all my gate configurations
**A:**
1. Check the backup: `ace_vars.cfg.backup`
2. Extract the `ace_gate_color`, `ace_gate_type`, `ace_gate_temp` arrays
3. Use `ACE_GATE_MAP` to reconfigure each gate

### Q: ace_device_map.cfg doesn't exist
**A:** It's created automatically on first run with auto_detect. If missing:
```gcode
FIRMWARE_RESTART
```

---

## Prevention

To avoid this issue in the future:

### 1. Use Auto-Detect
```ini
[ace_manager]
auto_detect: true
# This ensures proper device mapper initialization
```

### 2. Don't Manually Edit ace_vars.cfg
Let Klipper manage this file. Use G-code commands instead:
- `ACE_GATE_MAP` - Set gate properties
- `ACE_ENDLESS_SPOOL` - Enable/disable endless spool

### 3. Backup Regularly
```bash
# Add to cron or backup script
cp ~/printer_data/config/ace_vars.cfg ~/printer_data/config/backups/ace_vars_$(date +%Y%m%d).cfg
cp ~/printer_data/config/ace_device_map.cfg ~/printer_data/config/backups/ace_device_map_$(date +%Y%m%d).cfg
```

---

## Summary

✅ **Old code** wrote device properties to `ace_vars.cfg` with long keys → corruption
✅ **New code** writes device properties to `ace_device_map.cfg` → clean separation
✅ **Migration** is automatic - just clean up the corrupted file
✅ **Properties** now persist correctly across reboots and device changes

For more information, see:
- [USB_PORT_MAPPING_GUIDE.md](USB_PORT_MAPPING_GUIDE.md) - Device mapping system
- [DRYER_CONTROL_GUIDE.md](DRYER_CONTROL_GUIDE.md) - Per-device dryer control
