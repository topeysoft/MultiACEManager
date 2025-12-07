# KlipperACE Troubleshooting Guide

Common issues and solutions for KlipperACE installation and operation.

---

## Installation Issues

### Moonraker Component Error

**Error**: "An error was detected while loading the moonraker component 'ace_manager'"

**Causes**:
1. Import errors in ace_manager.py
2. Symlink not created correctly
3. File permissions issue
4. Moonraker version incompatibility

**Solutions**:

```bash
# Check Moonraker logs for detailed error
tail -50 ~/printer_data/logs/moonraker.log | grep -A10 ace_manager

# Verify symlink exists and is correct
ls -l ~/moonraker/moonraker/components/ace_manager.py
# Should point to: ~/KlipperACE/moonraker/ace_manager.py

# Check file permissions
chmod 644 ~/KlipperACE/moonraker/ace_manager.py

# Reinstall component
cd ~/KlipperACE
./install.sh

# Restart Moonraker
sudo systemctl restart moonraker
```

**Check Component Loading**:
```bash
# Watch Moonraker logs during restart
sudo systemctl restart moonraker && tail -f ~/printer_data/logs/moonraker.log
```

You should see:
```
ACE Manager Moonraker component initialized
```

---

## Klipper Issues

### ACE Extension Not Loading

**Error**: Module 'ace' not found

**Solutions**:

```bash
# Verify package installation
ls -la ~/klipper/klippy/extras/ace/

# Check Klipper logs
tail -50 ~/printer_data/logs/klippy.log | grep -i ace

# Restart Klipper
sudo systemctl restart klipper
```

### Python Import Errors

**Error**: "No module named 'serial'"

**Solution**:
```bash
# Install requirements
~/klippy-env/bin/pip install -r ~/KlipperACE/requirements.txt

# Verify pyserial is installed
~/klippy-env/bin/pip list | grep pyserial
```

---

## API Issues

### 404 Not Found on API Endpoints

**Error**: GET /server/ace/devices returns 404

**Causes**:
1. Moonraker component not loaded
2. [ace_manager] not in moonraker.conf
3. Moonraker not restarted

**Solutions**:

```bash
# Check moonraker.conf
grep -A2 "\[ace_manager\]" ~/printer_data/config/moonraker.conf

# If missing, add it
echo -e "\n[ace_manager]\n" >> ~/printer_data/config/moonraker.conf

# Restart Moonraker
sudo systemctl restart moonraker

# Test endpoint
curl http://localhost:7125/server/ace/devices
```

### Empty Device List

**Error**: API returns `"devices": []`

**Causes**:
1. No ACE devices configured in Klipper
2. ACE Manager not started
3. Devices not detected

**Solutions**:

```bash
# Check if ACE is configured in printer.cfg
grep -A10 "\[ace\]" ~/printer_data/config/printer.cfg

# Run device scan
# In Mainsail/Fluidd console:
ACE_LIST_DEVICES
ACE_SCAN_DEVICES

# Check for USB devices
ls /dev/ttyACM* /dev/ttyUSB*

# Check USB enumeration
lsusb | grep -i ACE
```

---

## Device Detection Issues

### No Devices Found During Scan

**Error**: ACE_SCAN_DEVICES finds 0 devices

**Diagnostic Steps**:

```bash
# 1. Check USB connections
lsusb

# 2. Check serial ports
ls -l /dev/ttyACM* /dev/ttyUSB* /dev/serial/by-id/

# 3. Check dmesg for USB events
dmesg | tail -20

# 4. Test serial port manually
python3 ~/KlipperACE/probe_ace_ports.py

# 5. Check permissions
groups $USER | grep -q dialout || echo "User not in dialout group"
```

**Add user to dialout group** (if needed):
```bash
sudo usermod -a -G dialout $USER
# Logout and login for changes to take effect
```

### Wrong Device Order

**Issue**: Devices appear in wrong order

**Solution**:

Use device mapping configuration:

```ini
# In printer.cfg
[ace]
auto_detect: true
device_map_file: ~/printer_data/config/ace_device_map.json
```

Or use manual serial ports in specific order:

```ini
[ace]
serial_ports: /dev/ttyACM0, /dev/ttyACM1, /dev/ttyACM2
```

---

## Runtime Issues

### WebSocket Connection Errors

**Error**: Mainsail shows "Disconnected" or "Connection Lost"

**Solutions**:

```bash
# Check Moonraker status
sudo systemctl status moonraker

# Check Moonraker logs
tail -100 ~/printer_data/logs/moonraker.log

# Restart Moonraker
sudo systemctl restart moonraker

# Check firewall
sudo ufw status
# Ensure port 7125 is allowed
```

### GCode Command Not Found

**Error**: "Unknown command: ACE_SCAN_DEVICES"

**Causes**:
1. ACE extension not loaded
2. Wrong ACE configuration (not using AceManager)

**Solutions**:

```bash
# Check available commands
# In console, type: HELP
# Look for ACE_ commands

# Check Klipper config
cat ~/printer_data/config/printer.cfg | grep -A10 "\[ace\]"

# Ensure using auto_detect or serial_ports for multi-device
# Single device won't have ACE_SCAN_DEVICES command
```

---

## Configuration Issues

### Invalid Configuration

**Error**: Klipper config error on startup

**Common Issues**:

1. **Missing extruder_sensor_pin**:
```ini
# WRONG:
[ace]
auto_detect: true

# CORRECT:
[ace]
auto_detect: true
extruder_sensor_pin: PG15  # Required!
```

2. **Conflicting configuration methods**:
```ini
# WRONG (using both):
[ace]
auto_detect: true
serial_ports: /dev/ttyACM0

# CORRECT (choose one):
[ace]
auto_detect: true
```

3. **Wrong section name**:
```ini
# WRONG:
[ace_manager]  # This is for moonraker.conf only!

# CORRECT (in printer.cfg):
[ace]
```

---

## Performance Issues

### Slow API Response

**Issue**: API endpoints take > 5 seconds to respond

**Solutions**:

```bash
# Check CPU usage
top -bn1 | grep -E "(klipper|moonraker)"

# Check for USB errors
dmesg | grep -i usb | tail -20

# Reduce polling frequency (in printer.cfg)
[ace]
status_poll_interval: 5.0  # Increase from default 2.0

# Check for cable issues
# Try different USB ports
# Use shorter, higher-quality USB cables
```

### Memory Usage

**Issue**: High memory consumption

**Check**:
```bash
# Memory usage
free -h

# Klipper memory
ps aux | grep klippy

# Moonraker memory
ps aux | grep moonraker
```

---

## Debugging Tips

### Enable Debug Logging

**For Klipper**:
```ini
# In printer.cfg
[ace]
log_level: debug  # Enable verbose logging
```

**For Moonraker**:
```bash
# Edit moonraker.conf (temporarily)
[server]
log_level: debug

# Restart
sudo systemctl restart moonraker

# Watch logs
tail -f ~/printer_data/logs/moonraker.log
```

### Test API Manually

```bash
# Test devices endpoint
curl -v http://localhost:7125/server/ace/devices

# Test scan endpoint
curl -X POST http://localhost:7125/server/ace/scan \
  -H "Content-Type: application/json" \
  -d '{"rescan": true}'

# Test status
curl http://localhost:7125/server/ace/status
```

### Check Service Status

```bash
# All printer services
sudo systemctl status klipper moonraker

# Detailed status
systemctl --no-pager status klipper
systemctl --no-pager status moonraker

# Recent logs
journalctl -u klipper -n 50 --no-pager
journalctl -u moonraker -n 50 --no-pager
```

---

## Getting Help

### Information to Provide

When reporting issues, include:

1. **System info**:
```bash
uname -a
cat /etc/os-release
```

2. **Klipper version**:
```bash
cd ~/klipper && git describe --tags
```

3. **Moonraker version**:
```bash
cd ~/moonraker && git describe --tags
```

4. **ACE configuration**:
```bash
grep -A20 "\[ace\]" ~/printer_data/config/printer.cfg
```

5. **Logs**:
```bash
tail -100 ~/printer_data/logs/klippy.log > klippy_error.log
tail -100 ~/printer_data/logs/moonraker.log > moonraker_error.log
```

### Community Support

- **GitHub Issues**: [Report bugs and feature requests]
- **Discord**: [Community chat and support]
- **Klipper Discourse**: [General Klipper help]

---

## Quick Fix Checklist

When something isn't working, try this checklist:

- [ ] Restart Klipper: `sudo systemctl restart klipper`
- [ ] Restart Moonraker: `sudo systemctl restart moonraker`
- [ ] Check logs: `tail -f ~/printer_data/logs/{klippy,moonraker}.log`
- [ ] Verify configuration: `grep "\[ace" ~/printer_data/config/*.conf`
- [ ] Test connectivity: `curl http://localhost:7125/server/info`
- [ ] Check USB devices: `ls /dev/ttyACM*`
- [ ] Reinstall: `cd ~/KlipperACE && ./install.sh`

---

**Last Updated**: November 26, 2025
