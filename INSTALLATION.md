# KlipperACE Installation Guide

Complete installation guide for KlipperACE with ACE Manager and Moonraker integration.

---

## Quick Install (Recommended)

### One-Command Installation

```bash
cd ~/
git clone https://github.com/yourusername/KlipperACE.git
cd KlipperACE
./install.sh
```

This will automatically:
- ✅ Install Klipper extension (modular `ace/` package)
- ✅ Install Moonraker component (`ace_manager.py`)
- ✅ Add `[ace_manager]` to moonraker.conf
- ✅ Add update manager configuration
- ✅ Copy example config files
- ✅ Install Python dependencies

---

## What Gets Installed

### 1. Klipper Extension
**Location**: `~/klipper/klippy/extras/ace/` (modular package)
- Provides AceController and modular architecture
- GCode commands (ACE_CHANGE_TOOL, ACE_STATUS, etc.)
- USB device auto-detection
- Multi-device management (up to 4 devices, 16 gates)

### 2. Moonraker Component
**File**: `~/moonraker/moonraker/components/ace_manager.py` (symlink)
- REST API endpoints for device management
- WebSocket support for real-time updates
- Integration with Mainsail/Fluidd

### 3. Configuration Files
**Location**: `~/printer_data/config/`
- `ace.cfg` - Example configuration
- `ace_vars.cfg` - Save variables template

### 4. Moonraker Configuration
**File**: `~/printer_data/config/moonraker.conf`
- Adds `[ace_manager]` section
- Adds `[update_manager KlipperACE]` section

---

## Manual Installation

If you prefer to install manually or need more control:

### Step 1: Clone Repository

```bash
cd ~/
git clone https://github.com/yourusername/KlipperACE.git
cd KlipperACE
```

### Step 2: Install Klipper Extension

The install script automatically creates the modular package structure. To do it manually:

```bash
# Create ace package directory
mkdir -p ~/klipper/klippy/extras/ace

# Link all modular files (see install.sh for complete list)
ln -sf ~/KlipperACE/extras/__init__.py ~/klipper/klippy/extras/ace/__init__.py
ln -sf ~/KlipperACE/extras/ace_controller.py ~/klipper/klippy/extras/ace/ace_controller.py
# ... (see install.sh for all files)
```

### Step 3: Install Moonraker Component

```bash
ln -sf ~/KlipperACE/moonraker/ace_manager.py ~/moonraker/moonraker/components/ace_manager.py
```

### Step 4: Install Python Dependencies

```bash
~/klippy-env/bin/pip install -r ~/KlipperACE/requirements.txt
```

### Step 5: Configure Moonraker

Add to `~/printer_data/config/moonraker.conf`:

```ini
# ACE Manager REST API component
[ace_manager]

# Update manager for KlipperACE
[update_manager KlipperACE]
type: git_repo
path: ~/KlipperACE
origin: https://github.com/yourusername/KlipperACE.git
primary_branch: main
managed_services: klipper moonraker
```

### Step 6: Copy Configuration Files

```bash
cp ~/KlipperACE/ace.cfg ~/printer_data/config/
cp ~/KlipperACE/ace_vars.cfg ~/printer_data/config/
```

### Step 7: Restart Services

```bash
sudo systemctl restart klipper
sudo systemctl restart moonraker
```

---

## Configuration

### Basic Configuration (Single ACE)

Add to your `printer.cfg`:

```ini
[include ace.cfg]

[ace]
serial: /dev/ttyACM0
extruder_sensor_pin: PG15
```

### Multi-Device Configuration (ACE Manager)

#### Option 1: Manual Serial Ports

```ini
[ace]
serial_ports: /dev/ttyACM0, /dev/ttyACM1
extruder_sensor_pin: PG15
toolhead_sensor_pin: PG12
```

#### Option 2: Auto-Detection (Recommended)

```ini
[ace]
auto_detect: true
extruder_sensor_pin: PG15
toolhead_sensor_pin: PG12
```

See [ace.cfg](ace.cfg) for a complete configuration example.

---

## Verification

### 1. Check Klipper Installation

```bash
# Verify symlink exists
ls -la ~/klipper/klippy/extras/ace/

# Should show modular package structure with symlinks
```

### 2. Check Moonraker Installation

```bash
# Verify component exists
ls -l ~/moonraker/moonraker/components/ace_manager.py

# Should show: ace_manager.py -> /home/pi/KlipperACE/moonraker/ace_manager.py
```

### 3. Check Moonraker Logs

```bash
tail -f ~/printer_data/logs/moonraker.log | grep -i ace
```

You should see:
```
ACE Manager Moonraker component initialized
```

### 4. Test Klipper Commands

In Mainsail/Fluidd console:

```gcode
ACE_LIST_DEVICES
ACE_SCAN_DEVICES
ACE_GET_STATUS
```

### 5. Test REST API

```bash
# Test devices endpoint
curl http://localhost:7125/server/ace/devices

# Test status endpoint
curl http://localhost:7125/server/ace/status
```

---

## Uninstallation

### Automatic Uninstall

```bash
cd ~/KlipperACE
./install.sh -u
```

This will remove:
- Klipper extension symlink
- Moonraker component symlink
- Display instructions for manual cleanup

### Manual Cleanup

After running uninstall script, you should also:

1. **Remove from printer.cfg**:
   ```ini
   # Remove or comment out:
   [include ace.cfg]
   [ace]
   ```

2. **Remove from moonraker.conf**:
   ```ini
   # Remove these sections:
   [ace_manager]
   [update_manager KlipperACE]
   ```

3. **Remove configuration files** (optional):
   ```bash
   rm ~/printer_data/config/ace.cfg
   rm ~/printer_data/config/ace_vars.cfg
   ```

4. **Delete repository** (optional):
   ```bash
   rm -rf ~/KlipperACE
   ```

5. **Restart services**:
   ```bash
   sudo systemctl restart klipper
   sudo systemctl restart moonraker
   ```

---

## Troubleshooting

### Installation Issues

#### "Klipper installation not found"
**Solution**: Verify Klipper is installed at `~/klipper`
```bash
ls ~/klipper/klippy/klippy.py
```

#### "Moonraker not found"
**Solution**: This is just a warning. Moonraker component will be skipped but Klipper extension will still work.

#### "Permission denied"
**Solution**: Don't run install.sh as root
```bash
# Run as your user (usually 'pi')
./install.sh
```

### Runtime Issues

#### "ACE Manager not found in Klipper"
**Causes**:
1. ACE not configured in printer.cfg
2. Klipper failed to load extension

**Solutions**:
```bash
# Check Klipper logs
tail -f ~/printer_data/logs/klippy.log | grep -i ace

# Verify configuration
cat ~/printer_data/config/printer.cfg | grep -A5 "\[ace\]"
```

#### "REST API returns 404"
**Causes**:
1. Moonraker component not installed
2. [ace_manager] not in moonraker.conf
3. Moonraker not restarted

**Solutions**:
```bash
# Verify component exists
ls -l ~/moonraker/moonraker/components/ace_manager.py

# Check moonraker.conf
grep -A2 "\[ace_manager\]" ~/printer_data/config/moonraker.conf

# Restart Moonraker
sudo systemctl restart moonraker
```

#### "No devices found"
**Causes**:
1. ACE devices not connected
2. USB permissions issue
3. Wrong serial ports

**Solutions**:
```bash
# List USB devices
ls /dev/ttyACM* /dev/ttyUSB*

# Check USB connections
lsusb | grep -i ACE

# Run device scan
# In Mainsail console:
ACE_SCAN_DEVICES
```

---

## Upgrading

### From Git (Recommended)

If you installed with git, use Moonraker's update manager:

1. Open Mainsail/Fluidd
2. Navigate to "Machine" → "Update Manager"
3. Find "KlipperACE" and click "Update"

### Manual Update

```bash
cd ~/KlipperACE
git pull
sudo systemctl restart klipper
sudo systemctl restart moonraker
```

---

## Platform-Specific Notes

### Raspberry Pi
- Default paths work out of the box
- Use `~/klipper`, `~/moonraker`, `~/printer_data`

### MIPS (e.g., Creality Sonic Pad)
- Script auto-detects MIPS architecture
- Uses `/usr/share/klipper` and `/usr/data/printer_data`
- Expects to run as root

### Other Linux Systems
- Verify paths in install.sh match your installation
- Edit variables at top of install.sh if needed:
  ```bash
  KLIPPER_HOME="${HOME}/klipper"
  MOONRAKER_HOME="${HOME}/moonraker"
  KLIPPER_CONFIG_HOME="${HOME}/printer_data/config"
  ```

---

## Next Steps

After successful installation:

1. **Configure ACE devices** - Edit printer.cfg with your ACE setup
2. **Restart services** - `sudo systemctl restart klipper moonraker`
3. **Test commands** - Run `ACE_LIST_DEVICES` in console
4. **Check Mainsail UI** - Open ACE Panel to see device management
5. **Read documentation**:
   - [MOONRAKER-INTEGRATION.md](MOONRAKER-INTEGRATION.md) - REST API usage
   - [PHASE2-IMPLEMENTATION-SUMMARY.md](PHASE2-IMPLEMENTATION-SUMMARY.md) - Feature overview
   - [README.md](README.md) - General usage guide

---

## Support

- **Issues**: https://github.com/yourusername/KlipperACE/issues
- **Documentation**: https://github.com/yourusername/KlipperACE/wiki
- **Discord**: [Your Discord link]

---

**Last Updated**: November 26, 2025
**Version**: 2.0.0 (Phase 2 - Web UI Integration)
