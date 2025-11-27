# ACE Manager - Moonraker Integration Guide

## Overview

This guide explains how to integrate the ACE Manager Moonraker component to enable REST API endpoints for web UI control.

---

## Installation

### 1. Install the Moonraker Component

Copy the ACE Manager Moonraker component to your Moonraker installation:

```bash
# Navigate to Moonraker components directory
cd ~/moonraker/moonraker/components

# Copy the ACE Manager component
cp /path/to/BunnyACE/moonraker/ace_manager.py ./

# Restart Moonraker
sudo systemctl restart moonraker
```

### 2. Configure Moonraker

Add the ACE Manager component to your `moonraker.conf`:

```ini
[ace_manager]
# ACE Manager component - no additional configuration needed
# This component automatically detects and exposes ACE devices via REST API
```

### 3. Verify Installation

Check that Moonraker loaded the component successfully:

```bash
# Check Moonraker logs
tail -f ~/printer_data/logs/moonraker.log | grep -i ace

# You should see:
# ACE Manager Moonraker component initialized
```

---

## API Endpoints

The ACE Manager Moonraker component provides four REST API endpoints:

### 1. GET /server/ace/devices

**Description**: List all ACE devices with detailed information

**Request**:
```http
GET http://localhost:7125/server/ace/devices
```

**Response**:
```json
{
  "devices": [
    {
      "device_id": "mac_001a2b3c",
      "name": "ACE Unit 1",
      "port": "/dev/ttyACM0",
      "model": "ACE PRO",
      "firmware": "v2.1.0",
      "connection_status": "connected",
      "gate_offset": 0,
      "num_gates": 4,
      "gates": [0, 1, 2, 3],
      "health": {
        "avg_response_time_ms": 45,
        "error_count": 0,
        "uptime": 3600
      }
    }
  ],
  "total_gates": 8,
  "num_devices": 2,
  "auto_detect_enabled": true
}
```

### 2. POST /server/ace/scan

**Description**: Trigger manual device scan

**Request**:
```http
POST http://localhost:7125/server/ace/scan
Content-Type: application/json

{
  "rescan": true,
  "update_map": true
}
```

**Response**:
```json
{
  "status": "success",
  "devices_found": 2,
  "new_devices": 0,
  "devices": [...]
}
```

### 3. POST /server/ace/reorder

**Description**: Reorder device gate assignments

**Request**:
```http
POST http://localhost:7125/server/ace/reorder
Content-Type: application/json

{
  "device_order": [
    {"device_id": "mac_00aabbcc", "gate_offset": 0},
    {"device_id": "mac_001a2b3c", "gate_offset": 4}
  ]
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Gate assignments updated. Restart Klipper to apply changes.",
  "restart_required": true
}
```

### 4. GET /server/ace/status

**Description**: Get current ACE Manager status with all gates and devices

**Request**:
```http
GET http://localhost:7125/server/ace/status
```

**Response**:
```json
{
  "status": "ready",
  "temp": 25,
  "num_gates": 8,
  "num_devices": 2,
  "gate_color": ["FF0000", "00FF00", "0000FF", "FFFF00", ...],
  "gate_material": ["PLA", "ABS", "PETG", "TPU", ...],
  "gate_temp": [200, 240, 230, 220, ...],
  "active_gate": ["ready", "ready", "empty", "ready", ...],
  "selected_gate": 0,
  "endless_spool": false,
  "devices": [...]
}
```

---

## Usage Examples

### cURL Examples

```bash
# List devices
curl http://localhost:7125/server/ace/devices

# Scan for devices
curl -X POST http://localhost:7125/server/ace/scan \
  -H "Content-Type: application/json" \
  -d '{"rescan": true, "update_map": true}'

# Get status
curl http://localhost:7125/server/ace/status

# Reorder devices
curl -X POST http://localhost:7125/server/ace/reorder \
  -H "Content-Type: application/json" \
  -d '{
    "device_order": [
      {"device_id": "mac_00aabbcc", "gate_offset": 0},
      {"device_id": "mac_001a2b3c", "gate_offset": 4}
    ]
  }'
```

### JavaScript/TypeScript Examples (Mainsail/Fluidd)

```typescript
// List devices
const response = await axios.get('/server/ace/devices')
const devices = response.data.devices

// Scan for devices
await axios.post('/server/ace/scan', {
  rescan: true,
  update_map: true
})

// Get status
const status = await axios.get('/server/ace/status')

// Reorder devices
await axios.post('/server/ace/reorder', {
  device_order: [
    { device_id: 'mac_00aabbcc', gate_offset: 0 },
    { device_id: 'mac_001a2b3c', gate_offset: 4 }
  ]
})
```

---

## Integration with Mainsail/Fluidd

The Moonraker component is designed to work seamlessly with Mainsail and Fluidd web interfaces:

### Mainsail Integration

The enhanced Mainsail ACE Panel (Phase 2 implementation) automatically uses these REST endpoints:

1. **Device Tab**: Calls `/server/ace/devices` to populate device cards
2. **Scan Button**: Triggers `/server/ace/scan` when clicked
3. **Status Updates**: Subscribes to WebSocket updates for real-time device status

### Fluidd Integration

Similar integration can be added to Fluidd using the same REST endpoints.

---

## WebSocket Notifications

The ACE Manager component supports real-time updates via Moonraker's WebSocket:

### Subscribe to ACE Status Updates

```javascript
// Subscribe to ACE object updates
socket.emit('subscribe_objects', {
  ace: ['status', 'devices', 'num_devices', 'gate_color', 'active_gate']
})

// Handle updates
socket.on('notify_status_update', (data) => {
  if (data.ace) {
    // Update UI with new ACE status
    console.log('ACE status updated:', data.ace)
  }
})
```

---

## Troubleshooting

### Component Not Loading

**Symptom**: Endpoints return 404 or component not found in logs

**Solution**:
1. Verify `ace_manager.py` is in `~/moonraker/moonraker/components/`
2. Check file permissions: `chmod 644 ace_manager.py`
3. Restart Moonraker: `sudo systemctl restart moonraker`
4. Check logs: `tail -f ~/printer_data/logs/moonraker.log`

### ACE Manager Not Found in Klipper

**Symptom**: API returns "ACE Manager not found in Klipper"

**Solution**:
1. Verify ACE Manager is configured in `printer.cfg`
2. Ensure Klipper is running: `sudo systemctl status klipper`
3. Check Klipper logs: `tail -f ~/printer_data/logs/klippy.log`

### Device Scan Returns No Devices

**Symptom**: `/server/ace/scan` returns `devices_found: 0`

**Solution**:
1. Check USB connections to ACE devices
2. Verify ACE devices are powered on
3. Run manual scan: `ACE_SCAN_DEVICES` in console
4. Check dmesg for USB enumeration: `dmesg | grep -i ACE`

### Reorder Fails

**Symptom**: `/server/ace/reorder` returns error

**Solution**:
1. Verify all device IDs are correct
2. Ensure gate offsets are multiples of 4
3. Check no overlapping gate assignments
4. Verify `ACE_REORDER_DEVICES` GCode command exists

---

## Security Considerations

### API Access Control

Moonraker's authorization system protects ACE endpoints:

```ini
# In moonraker.conf
[authorization]
trusted_clients:
    192.168.1.0/24
    127.0.0.1

cors_domains:
    http://mainsail.local
    http://fluidd.local
```

### HTTPS/TLS

For production deployments, enable HTTPS:

```ini
# In moonraker.conf
[server]
ssl_certificate: /path/to/cert.pem
ssl_key_file: /path/to/key.pem
```

---

## Performance Considerations

1. **Device Scanning**: Manual scans take ~1-2 seconds per device
2. **Status Updates**: Polled every 2 seconds via WebSocket
3. **Endpoint Response Times**:
   - GET requests: < 50ms
   - POST scan: 1-3 seconds
   - POST reorder: < 100ms

---

## Future Enhancements

Planned features for future releases:

- [ ] Device firmware update via API
- [ ] Advanced health metrics (temperature, vibration)
- [ ] Device configuration export/import
- [ ] Automatic device naming based on location
- [ ] Multi-device print statistics
- [ ] Device-specific error logs

---

## Contributing

To contribute to the Moonraker integration:

1. Fork the repository
2. Add features to `moonraker/ace_manager.py`
3. Test with actual ACE hardware
4. Submit pull request with documentation

---

## References

- [Moonraker Documentation](https://moonraker.readthedocs.io/)
- [ACE Manager Phase 2 Implementation](PHASE2-IMPLEMENTATION-SUMMARY.md)
- [Klipper API Documentation](https://www.klipper3d.org/API_Server.html)

---

**Last Updated**: November 26, 2025
**Version**: 1.0.0
