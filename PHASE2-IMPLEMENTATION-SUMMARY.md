# ACE Manager Phase 2: Web UI Integration - Implementation Summary

## Overview
Phase 2 implementation adds comprehensive multi-device management capabilities to the ACE Manager system, with full Web UI integration for Mainsail.

**Implementation Date**: November 26, 2025
**Status**: ✅ Backend Complete | ✅ Mainsail UI Complete | ✅ Moonraker Integration Complete

---

## ✅ Completed Components

### 1. Backend Enhancements ([BunnyACE/extras/ace.py](extras/ace.py))

#### New Methods in AceManager Class

**`get_device_list()` (Line ~2086)**
- Returns detailed information about all ACE devices
- Includes device ID, name, port, model, firmware version
- Provides connection status and health metrics
- Used by Moonraker API for `/printer/ace/devices` endpoint

**`_get_device_health(ace_instance)` (Line ~2118)**
- Extracts health metrics from ACE device instances
- Returns avg response time, error count, uptime
- Supports extensible health tracking system

**`scan_devices(rescan=True, update_map=True)` (Line ~2141)**
- Manual device scanning via USB enumeration
- Detects new ACE devices and updates device map
- Returns scan results with new device list
- Used by Moonraker API for `/printer/ace/scan` endpoint

**`reorder_gates(device_order)` (Line ~2198)**
- Reorders gate assignments for devices
- Validates device order and gate offset constraints
- Updates device mapper and persists changes
- Requires Klipper restart to apply changes

#### Enhanced get_status() Method (Line ~2020)

**New Device Summary Field**
```python
'devices': [
    {
        'device_id': 'mac_001a2b3c',
        'name': 'ACE Unit 1',
        'connection_status': 'connected',
        'gate_offset': 0,
        'health': {...}
    },
    ...
]
```

#### New GCode Commands

**`ACE_SCAN_DEVICES` (Line ~2335)**
- Trigger manual device scan from console/web UI
- Displays scan results with device details
- Reports new devices found during scan

**`ACE_LIST_DEVICES` (Line ~2361)**
- List all ACE devices with status and health
- Shows connection status, uptime, error counts
- Formatted output for console viewing

### 2. Mainsail UI Enhancements

#### Enhanced ACE Mixin ([mainsail/src/components/mixins/ace.ts](../mainsail-crew/mainsail/src/components/mixins/ace.ts))

**New Device Management Getters**
- `aceDevices` - Array of all ACE devices
- `aceNumDevices` - Total number of devices
- `aceHasMultipleDevices` - Boolean for multi-device setups
- `aceHasDisconnectedDevices` - Health check indicator

**New Helper Methods**
- `getAceDevice(deviceId)` - Get device by ID
- `getAceDeviceForGate(gateIndex)` - Find device for specific gate
- `aceScanDevices()` - Trigger device scan
- `aceListDevices()` - List all devices
- `getAceDeviceStatus(deviceId)` - Get connection status
- `getAceDeviceHealth(deviceId)` - Get health metrics
- `getAceDeviceUptimeFormatted(deviceId)` - Formatted uptime string

#### New Components

**AcePanelDeviceCard.vue** ([mainsail/src/components/panels/Ace/](../mainsail-crew/mainsail/src/components/panels/Ace/AcePanelDeviceCard.vue))
- Visual card component for individual device display
- Shows device name, model, firmware, port
- Connection status indicator with color coding
- Health metrics: uptime, error count, response time
- Responsive design with hover effects

**AcePanelDeviceList.vue** ([mainsail/src/components/panels/Ace/](../mainsail-crew/mainsail/src/components/panels/Ace/AcePanelDeviceList.vue))
- Container component for device management
- Grid layout of device cards
- "Scan Devices" button with loading state
- Warning alert for disconnected devices
- Empty state with scan prompt

#### Enhanced AcePanel.vue ([mainsail/src/components/panels/](../mainsail-crew/mainsail/src/components/panels/AcePanel.vue))
- **New Tab System**:
  - "Gates" tab - Original gate management view
  - "Devices" tab - Multi-device management view
  - Only shown when `aceHasMultipleDevices` is true
- Maintains backward compatibility for single-device setups
- Dynamic tab switching with active state tracking

#### Localization ([mainsail/src/locales/en.json](../mainsail-crew/mainsail/src/locales/en.json))

**New Translation Keys**
```json
{
  "Gates": "Gates",
  "Devices": "Devices",
  "DeviceManagement": "Device Management",
  "ScanDevices": "Scan Devices",
  "DisconnectedDevicesWarning": "One or more ACE devices are disconnected...",
  "NoDevicesFound": "No ACE devices found",
  "ScanForDevices": "Scan for Devices",
  "DeviceScanStarted": "Device scan started",
  "DeviceScanFailed": "Failed to scan for devices"
}
```

---

## 🔧 Technical Architecture

### Data Flow
```
┌──────────────┐      WebSocket      ┌──────────────┐
│  Mainsail UI │ ◄─────────────────► │  Moonraker   │
└──────────────┘                     └──────────────┘
      │                                      │
      │ GCode Commands                      │
      │ (ACE_SCAN_DEVICES)                  │ Unix Socket
      ▼                                      ▼
┌──────────────┐                     ┌──────────────┐
│ Console/API  │                     │   Klippy     │
└──────────────┘                     └──────────────┘
                                             │
                                             ▼
                                     ┌──────────────┐
                                     │  AceManager  │
                                     │  get_status()│
                                     │  get_device_ │
                                     │  list()      │
                                     └──────────────┘
                                             │
                                   ┌─────────┼─────────┐
                                   ▼         ▼         ▼
                              ┌────────┬────────┬────────┐
                              │ ACE #1 │ ACE #2 │ ACE #3 │
                              └────────┴────────┴────────┘
```

### Key Design Decisions

1. **Backward Compatibility**
   - Single-device setups see no UI changes
   - Multi-device tab only appears when needed
   - Existing ACE commands still work

2. **Device Health Tracking**
   - Extensible health metrics system
   - Supports uptime, error counts, response times
   - Future expansion for firmware updates, diagnostics

3. **USB-Based Device Discovery**
   - Leverages existing AceDeviceDiscovery class
   - VID/PID matching for reliable detection
   - Stable device ordering via USB location

4. **Component Architecture**
   - Reusable device card component
   - Separation of concerns (card vs list)
   - Lazy-loaded for performance

---

## 🌐 Moonraker Integration ([moonraker/ace_manager.py](moonraker/ace_manager.py))

### Component Structure

**Location**: `~/moonraker/moonraker/components/ace_manager.py`

**Key Features**:
- Standard Moonraker component with `load_component()` function
- Registers 4 REST API endpoints
- Communicates with Klipper via `klippy_apis`
- Supports both HTTP and WebSocket transports

### REST API Endpoints

#### 1. GET /server/ace/devices
- Lists all ACE devices with health metrics
- Returns device ID, name, port, firmware, connection status
- Includes health data (uptime, errors, response time)

#### 2. POST /server/ace/scan
- Triggers manual USB device scan
- Executes `ACE_SCAN_DEVICES` GCode command
- Returns updated device list with new devices count

#### 3. POST /server/ace/reorder
- Reorders device gate assignments
- Validates device order and gate offsets
- Executes `ACE_REORDER_DEVICES` GCode command
- Returns restart_required flag

#### 4. GET /server/ace/status
- Returns full ACE Manager status
- Includes all gates, materials, colors, temperatures
- Provides device summary array

### New GCode Command

**`ACE_REORDER_DEVICES`** (Line ~2404)
- Accepts JSON-encoded device order via ORDER parameter
- Validates and applies new gate assignments
- Updates device mapper configuration
- Prompts for Klipper restart

### Installation

```bash
# Copy component to Moonraker
cp moonraker/ace_manager.py ~/moonraker/moonraker/components/

# Add to moonraker.conf
[ace_manager]

# Restart Moonraker
sudo systemctl restart moonraker
```

See [MOONRAKER-INTEGRATION.md](MOONRAKER-INTEGRATION.md) for complete installation and usage guide.

---

## 📋 Pending Items

### Critical
- [x] **Moonraker REST API Integration** ✅ COMPLETE
  - [x] Determine where Moonraker plugins live
  - [x] Implement `/server/ace/devices` endpoint
  - [x] Implement `/server/ace/scan` endpoint
  - [x] Implement `/server/ace/reorder` endpoint
  - [x] Implement `/server/ace/status` endpoint
  - [x] Add `ACE_REORDER_DEVICES` GCode command

### Nice to Have
- [ ] Device rename functionality
- [ ] Drag-and-drop device reordering UI
- [ ] Device firmware update support
- [ ] Advanced health metrics (temperature, vibration)
- [ ] KlipperScreen device management UI

---

## 🧪 Testing Checklist

### Backend
- [ ] Test `get_device_list()` with 1, 2, 3+ devices
- [ ] Test `scan_devices()` discovery logic
- [ ] Test `reorder_gates()` validation
- [ ] Test GCode commands in console
- [ ] Test health metrics collection

### Frontend
- [ ] Test single-device setup (no tabs)
- [ ] Test multi-device setup (with tabs)
- [ ] Test device card rendering
- [ ] Test scan button functionality
- [ ] Test disconnected device warnings
- [ ] Test responsive design on mobile
- [ ] Test localization strings

### Integration
- [ ] Test WebSocket status updates
- [ ] Test device status polling
- [ ] Test connection state changes
- [ ] Test error handling

---

## 📝 Usage Examples

### Console Commands

```gcode
# Scan for ACE devices
ACE_SCAN_DEVICES

# List all devices
ACE_LIST_DEVICES

# Get unified status
ACE_GET_STATUS
```

### Python API

```python
# In Klipper plugins or Moonraker
ace_manager = printer.lookup_object('ace')

# Get device list
devices = ace_manager.get_device_list()

# Scan for devices
result = ace_manager.scan_devices(rescan=True, update_map=True)

# Reorder devices
ace_manager.reorder_gates([
    {'device_id': 'mac_00aabbcc', 'gate_offset': 0},
    {'device_id': 'mac_001a2b3c', 'gate_offset': 4}
])
```

### Mainsail UI

**For Users:**
1. Navigate to ACE Panel
2. If multiple devices: click "Devices" tab
3. View all connected ACE units
4. Click "Scan Devices" to refresh
5. Monitor health metrics (uptime, errors)

---

## 🎯 Next Steps

1. **Moonraker Integration** (HIGH PRIORITY)
   - Research Moonraker plugin architecture
   - Implement REST endpoints
   - Test API with Mainsail

2. **Device Reordering UI** (MEDIUM PRIORITY)
   - Create drag-and-drop dialog
   - Implement reorder confirmation
   - Add restart prompt

3. **KlipperScreen Support** (LOW PRIORITY)
   - Enhance `panels/ace.py`
   - Add device list view
   - Add scan button

4. **Documentation** (MEDIUM PRIORITY)
   - User guide for multi-device setup
   - API documentation
   - Troubleshooting guide

---

## 📚 References

- [IMPLEMENTATION-PHASE2.md](IMPLEMENTATION-PHASE2.md) - Original specification
- [ace.py](extras/ace.py) - Backend implementation
- [AcePanel.vue](../mainsail-crew/mainsail/src/components/panels/AcePanel.vue) - UI implementation
- [ace.ts](../mainsail-crew/mainsail/src/components/mixins/ace.ts) - Mixin implementation

---

## 🤝 Contributing

To extend this implementation:

1. **Backend**: Add methods to `AceManager` class
2. **Frontend**: Create new components in `Ace/` folder
3. **Localization**: Update `locales/en.json` and other languages
4. **Testing**: Add tests to validate functionality

---

**Implementation Team**: Claude Code Assistant
**Last Updated**: November 26, 2025
**Version**: Phase 2.0 - Initial Release
