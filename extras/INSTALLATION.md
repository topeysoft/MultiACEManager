# ACE Pro Installation Guide

## What Gets Installed

The KlipperACE installation script (`install.sh`) installs both the legacy and new modular architecture simultaneously.

### Klipper Extension Installation

The script creates the following structure in your Klipper installation:

```
~/klipper/klippy/extras/
├── ace.py                           # Legacy (backward compatible)
└── ace/                             # New modular architecture
    ├── __init__.py                  # Package entry with feature flag
    ├── exceptions.py
    ├── ace_controller.py
    ├── protocol/
    │   ├── __init__.py
    │   ├── constants.py
    │   └── packet.py
    ├── device/
    │   ├── __init__.py
    │   ├── ace_device.py
    │   ├── device_manager.py
    │   ├── device_discovery.py
    │   └── device_mapper.py
    ├── sensors/
    │   ├── __init__.py
    │   └── runout_helper.py
    └── commands/
        ├── __init__.py
        ├── tool_commands.py
        ├── config_commands.py
        └── status_commands.py
```

All files are symlinked (not copied), so updates to the KlipperACE repository automatically reflect in Klipper.

## Installation Steps

### 1. Clone the Repository

```bash
cd ~
git clone https://github.com/your-repo/KlipperACE.git
cd KlipperACE
```

### 2. Run the Installation Script

```bash
./install.sh
```

The script will:
- ✅ Stop Klipper
- ✅ Link ace.py (legacy)
- ✅ Create ace/ package directory structure
- ✅ Link all modular architecture files
- ✅ Copy configuration files (ace.cfg, ace_vars.cfg, etc.)
- ✅ Install Moonraker component (if available)
- ✅ Add update manager section to moonraker.conf
- ✅ Restart Klipper

### 3. Configure Klipper

Add to your `printer.cfg`:

```ini
[include ace.cfg]
```

**Or** for auto-detection:
```ini
[include ace_manager_auto_detect.cfg]
```

### 4. (Optional) Enable New Architecture

To use the modular architecture instead of legacy, add to your `[ace]` section:

```ini
[ace]
use_new_architecture: True
# ... rest of your ACE config
```

### 5. Restart Services

```bash
sudo systemctl restart klipper moonraker
```

## What Architecture Is Used?

### By Default: Legacy (ace.py)

When you first install, the system uses the legacy `ace.py` file for 100% backward compatibility.

```ini
[ace]
serial: /dev/ttyACM0
# No use_new_architecture line = legacy mode
```

### Opt-In: New Modular Architecture

Add the feature flag to switch to the new architecture:

```ini
[ace]
use_new_architecture: True
serial: /dev/ttyACM0
```

The new architecture provides:
- ✅ Modular code (18 files instead of 1)
- ✅ Enhanced multi-device support
- ✅ Better error handling
- ✅ Improved status commands
- ✅ Cleaner separation of concerns

## Verification

After installation, verify both architectures are available:

```bash
# Check legacy
ls -la ~/klipper/klippy/extras/ace.py

# Check new architecture
ls -la ~/klipper/klippy/extras/ace/
```

You should see symlinks pointing back to your KlipperACE directory.

## Uninstallation

To remove KlipperACE:

```bash
cd ~/KlipperACE
./install.sh -u
```

This will:
- ✅ Remove `ace.py` symlink
- ✅ Remove `ace/` package directory
- ✅ Remove Moonraker component
- ⚠️ Keep configuration files (manual removal required)

## Troubleshooting

### Issue: Klipper fails to start

**Check:**
```bash
tail -f ~/printer_data/logs/klippy.log
```

**Common causes:**
- Missing `[save_variables]` section
- Incorrect sensor pin configuration
- Python import errors

**Fix:**
1. Verify your `ace.cfg` has proper configuration
2. Ensure `ace_vars.cfg` exists and is valid
3. Check that `use_new_architecture` is set correctly (True/False, not yes/no)

### Issue: Import errors with new architecture

**Check:**
```bash
ls -la ~/klipper/klippy/extras/ace/
```

All files should be symlinks pointing to `~/KlipperACE/extras/`

**Fix:**
```bash
cd ~/KlipperACE
./install.sh -u
./install.sh
```

### Issue: Want to switch between architectures

Simply change the config and restart Klipper:

```ini
# Use legacy
[ace]
#use_new_architecture: True  # Comment out or remove
serial: /dev/ttyACM0

# Use new architecture
[ace]
use_new_architecture: True
serial: /dev/ttyACM0
```

Then:
```bash
sudo systemctl restart klipper
```

## Directory Structure Reference

### Installation Creates

```
~/klipper/klippy/extras/
├── ace.py -> ~/KlipperACE/extras/ace.py
└── ace/
    ├── __init__.py -> ~/KlipperACE/extras/__init__.py
    ├── ace_controller.py -> ~/KlipperACE/extras/ace_controller.py
    ├── exceptions.py -> ~/KlipperACE/extras/exceptions.py
    ├── protocol/
    │   ├── __init__.py -> ~/KlipperACE/extras/protocol/__init__.py
    │   ├── constants.py -> ~/KlipperACE/extras/protocol/constants.py
    │   └── packet.py -> ~/KlipperACE/extras/protocol/packet.py
    ├── device/
    │   ├── __init__.py -> ~/KlipperACE/extras/device/__init__.py
    │   ├── ace_device.py -> ~/KlipperACE/extras/device/ace_device.py
    │   ├── device_manager.py -> ~/KlipperACE/extras/device/device_manager.py
    │   ├── device_discovery.py -> ~/KlipperACE/extras/device/device_discovery.py
    │   └── device_mapper.py -> ~/KlipperACE/extras/device/device_mapper.py
    ├── sensors/
    │   ├── __init__.py -> ~/KlipperACE/extras/sensors/__init__.py
    │   └── runout_helper.py -> ~/KlipperACE/extras/sensors/runout_helper.py
    └── commands/
        ├── __init__.py -> ~/KlipperACE/extras/commands/__init__.py
        ├── tool_commands.py -> ~/KlipperACE/extras/commands/tool_commands.py
        ├── config_commands.py -> ~/KlipperACE/extras/commands/config_commands.py
        └── status_commands.py -> ~/KlipperACE/extras/commands/status_commands.py
```

### Configuration Files Created

```
~/printer_data/config/
├── ace.cfg                         # Main ACE configuration
├── ace_vars.cfg                    # Persistent variables
├── ace_dryer_macros.cfg            # Dryer control macros (optional)
└── ace_manager_auto_detect.cfg     # Auto-detect example config
```

## Benefits of This Approach

### Dual Installation
- Both legacy and new architectures installed
- Switch between them with a single config line
- No reinstallation required

### Symlinks
- Updates to KlipperACE repo automatically apply
- Easy to develop and test
- No file copying

### Zero Risk
- Legacy works by default
- New architecture is opt-in
- Can rollback instantly

## Next Steps

After installation:
1. Read [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for architecture migration details
2. Read [ARCHITECTURE.md](ARCHITECTURE.md) for technical documentation
3. Test with `ACE_GET_STATUS` command
4. Optionally enable new architecture with `use_new_architecture: True`

---

*Last Updated: 2025-11-29*
