# KlipperACE Quick Reference Card

## 🚀 5-Minute Multi-ACE Setup

```bash
# 1. Auto-detect ACE devices and generate config
cd ~/printer_data/config
python3 ~/KlipperACE/probe_ace_ports.py --generate-config

# 2. Copy output to ace.cfg

# 3. Edit two lines:
#    - extruder_sensor_pin: YOUR_PIN
#    - toolhead_sensor_pin: YOUR_PIN

# 4. Restart Klipper
sudo systemctl restart klipper

# 5. Test
# In console: ACE_GET_STATUS
```

## 📋 Configuration Cheat Sheet

### Method 1: Serial Ports (Recommended)

```ini
[ace]
serial_ports: /dev/ttyACM0, /dev/ttyACM1
extruder_sensor_pin: ^EBBCan: PB9
feed_speed: 80
```

### Method 2: Auto-Detect
```ini
[ace]
auto_detect: true
extruder_sensor_pin: ^EBBCan: PB9
```

## 🎯 Gate Number Reference

| # ACEs | Total Gates | T Commands | Config File |
|--------|-------------|------------|-------------|
| 1      | 4           | T0-T3      | ace.cfg |
| 2      | 8           | T0-T7      | ace.cfg |
| 3      | 12          | T0-T11     | ace.cfg |
| 4      | 16          | T0-T15     | ace.cfg |

### Gate Mapping
```
ACE 1: Local 0-3 → Global 0-3  → T0-T3
ACE 2: Local 0-3 → Global 4-7  → T4-T7
ACE 3: Local 0-3 → Global 8-11 → T8-T11
ACE 4: Local 0-3 → Global 12-15 → T12-T15
```

## 🛠️ Common Commands

### Detection
```bash
# Find ACE ports
python3 probe_ace_ports.py -v

# Test specific port
python3 probe_ace_ports.py /dev/ttyACM0

# List USB devices
ls -la /dev/ttyACM*
```

### Testing
```gcode
ACE_GET_STATUS              # Show all gates
ACE_GET_STATUS VERBOSE=1    # Show gate colors/materials/temps
ACE_CHANGE_TOOL TOOL=0      # Load gate 0
ACE_CHANGE_TOOL TOOL=-1     # Unload current
T0                          # Quick load gate 0
T4                          # Quick load gate 4 (ACE 2)
ACE_SET_GATE GATE=2         # Mark gate 2 as selected (manual load)
ACE_CLEAR_SELECTION         # Clear gate selection (manual unload)
ACE_SCAN_DEVICES VERBOSE=1  # Scan USB for ACE devices
ACE_LIST_DEVICES            # List connected devices
ACE_LIST_ALIASES            # Show device aliases
ACE_GET_DRYER_STATUS        # Show all dryer statuses
ACE_RETRY_FEED              # Retry after feed timeout
ACE_CANCEL_FEED             # Cancel after feed timeout
```

### Debugging
```bash
# Check Klipper logs
tail -f /tmp/klippy.log | grep ACE

# Restart Klipper
sudo systemctl restart klipper

# Check Klipper status
sudo systemctl status klipper
```

## 🔧 Essential Parameters

### Must Configure
```ini
serial_ports: /dev/ttyACM0, /dev/ttyACM1  # Your ACE ports
extruder_sensor_pin: ^EBBCan: PB9         # Your sensor pin
```

### Should Tune
```ini
toolchange_retract_length: 170  # Splitter to extruder distance
toolhead_sensor_to_nozzle: 40   # Sensor to nozzle distance
```

### Can Adjust
```ini
feed_speed: 80           # Filament feed speed
retract_speed: 80        # Filament retract speed
```

## 🐛 Troubleshooting Quick Fixes

### "No ACE devices detected"
```bash
# Stop Klipper first!
sudo systemctl stop klipper
python3 probe_ace_ports.py -v
sudo systemctl start klipper
```

### "Cannot find sensor pin"
```ini
# For EBB CAN boards:
extruder_sensor_pin: ^EBBCan: PB9

# For local pins:
extruder_sensor_pin: ^PG15
```

### Wrong gate numbers
```ini
# Gates assigned by port order
# To swap ACE1 ↔ ACE2, swap port order:
serial_ports: /dev/ttyACM1, /dev/ttyACM0
```

### Commands not found
```bash
# Install/reinstall ACE package
cd ~/KlipperACE
./install.sh
sudo systemctl restart klipper
```

## 📁 File Locations

```
~/KlipperACE/                              # Repo
  ├── extras/                            # Modular package
  │   ├── __init__.py                    # Entry point
  │   ├── ace_controller.py              # Main controller
  │   ├── protocol/                      # Protocol layer
  │   ├── device/                        # Device layer
  │   ├── sensors/                       # Sensors layer
  │   └── commands/                      # Commands layer
  ├── probe_ace_ports.py                 # Detection tool
  └── install.sh                         # Installation script

~/printer_data/config/                   # Klipper config
  ├── printer.cfg                        # Main config
  ├── ace.cfg                            # ACE config (include this)
  └── ace_vars.cfg                       # Variables (auto-created)

~/klipper/klippy/extras/                 # Klipper modules
  └── ace/                               # Installed package (symlinks)
```

## 📚 Documentation Map

| Document | Purpose | Read Time |
|----------|---------|-----------|
| **[README.md](./README.md)** | Overview + Quick Start | 15 min |
| **[CONFIGURATION_REFERENCE.md](./CONFIGURATION_REFERENCE.md)** | All config parameters | 10 min |
| **[FEED_RECOVERY_GUIDE.md](./FEED_RECOVERY_GUIDE.md)** | Feed timeout recovery | 5 min |
| **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** | Common issues & fixes | 10 min |
| **[DEVICE_ALIASING_GUIDE.md](./DEVICE_ALIASING_GUIDE.md)** | Friendly device naming | 5 min |
| **[DRYER_CONTROL_GUIDE.md](./DRYER_CONTROL_GUIDE.md)** | Per-device dryer control | 10 min |
| **[USB_PORT_MAPPING_GUIDE.md](./USB_PORT_MAPPING_GUIDE.md)** | USB device identification | 10 min |
| **[MOONRAKER-INTEGRATION.md](./MOONRAKER-INTEGRATION.md)** | REST API reference | 10 min |

## 🎨 Example Workflows

### Adding a Third ACE
```ini
# Before (8 gates):
serial_ports: /dev/ttyACM0, /dev/ttyACM1

# After (12 gates):
serial_ports: /dev/ttyACM0, /dev/ttyACM1, /dev/ttyACM2

# Uncomment T8-T11 macros
# Restart Klipper
```

### Testing New ACE
```bash
# 1. Physical: Connect ACE
# 2. Detect: python3 probe_ace_ports.py -v
# 3. Identify: Note the new port
# 4. Add to config: serial_ports: ..., /dev/ttyACMX
# 5. Restart: sudo systemctl restart klipper
# 6. Test: T8 (for 3rd ACE)
```

### Swapping Filament
```gcode
# Manual load to gate 2:
T2

# Auto-switch on runout (Endless Spool):
# Set in slicer or macro
```

## 💡 Pro Tips

1. **Use by-id paths** for stability:
   ```ini
   # Instead of: /dev/ttyACM0
   # Use: /dev/serial/by-id/usb-ANYCUBIC_ACE_1-if00
   ```

2. **Generate config** instead of typing:
   ```bash
   python3 probe_ace_ports.py --generate-config > ace_temp.cfg
   ```

3. **Test ports** before Klipper config:
   ```bash
   python3 probe_ace_ports.py /dev/ttyACM0 /dev/ttyACM1
   ```

4. **Check logs** on any error:
   ```bash
   tail -20 /tmp/klippy.log
   ```

5. **Backup config** before changes:
   ```bash
   cp ~/printer_data/config/ace.cfg ~/ace.cfg.backup
   ```

## 🔗 Quick Links

- **GitHub:** https://github.com/topeysoft/MultiACEManager
- **Issues:** Report bugs and ask questions
- **Wiki:** Community tips and tricks

## 🎯 Minimal Working Config

```ini
[save_variables]
filename: ~/printer_data/config/ace_vars.cfg

[respond]

[ace_manager]
serial_ports: /dev/ttyACM0, /dev/ttyACM1
extruder_sensor_pin: ^EBBCan: PB9

[gcode_macro T0]
gcode: ACE_CHANGE_TOOL TOOL=0

[gcode_macro T1]
gcode: ACE_CHANGE_TOOL TOOL=1

[gcode_macro T2]
gcode: ACE_CHANGE_TOOL TOOL=2

[gcode_macro T3]
gcode: ACE_CHANGE_TOOL TOOL=3

[gcode_macro T4]
gcode: ACE_CHANGE_TOOL TOOL=4

[gcode_macro T5]
gcode: ACE_CHANGE_TOOL TOOL=5

[gcode_macro T6]
gcode: ACE_CHANGE_TOOL TOOL=6

[gcode_macro T7]
gcode: ACE_CHANGE_TOOL TOOL=7
```

**That's it!** Add your macros (POOP, CUT_TIP, etc.) and tune distances.

---

**Last Updated:** 2026-02-26
**For:** KlipperACE v2.0+ with multi-ACE support
