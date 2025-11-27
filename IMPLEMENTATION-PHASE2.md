# ACE Manager - Phase 2: Web UI Integration

## Overview
Phase 2 adds comprehensive web UI support for Mainsail and Fluidd, providing visual device management, gate configuration, and monitoring capabilities directly from the browser.

## Architecture

### 1. Moonraker API Extensions

#### New Moonraker Endpoints

##### GET /printer/ace/devices
**Description**: List all detected ACE devices with status

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
      "last_seen": 1234567890,
      "uptime": 3600,
      "health": {
        "avg_response_time_ms": 45,
        "error_count": 0,
        "last_error": null
      }
    },
    {
      "device_id": "mac_00aabbcc",
      "name": "ACE Unit 2",
      "port": "/dev/ttyACM1",
      "model": "ACE PRO",
      "firmware": "v2.1.0",
      "connection_status": "connected",
      "gate_offset": 4,
      "num_gates": 4,
      "gates": [4, 5, 6, 7],
      "last_seen": 1234567891,
      "uptime": 3600,
      "health": {
        "avg_response_time_ms": 42,
        "error_count": 0,
        "last_error": null
      }
    }
  ],
  "total_gates": 8,
  "auto_detect_enabled": true,
  "device_map_file": "/home/pi/printer_data/config/ace_device_map.cfg"
}
```

##### POST /printer/ace/scan
**Description**: Manually trigger device scan

**Request**:
```json
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

##### POST /printer/ace/reorder
**Description**: Reorder gate assignments

**Request**:
```json
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
  "message": "Gate assignments updated. Restart required.",
  "restart_required": true
}
```

##### GET /printer/ace/status
**Description**: Get detailed status of all ACE devices (enhanced version of existing endpoint)

**Response**:
```json
{
  "status": "ready",
  "temp": 25,
  "dryer_status": {
    "status": "stop",
    "target_temp": 0,
    "duration": 0,
    "remain_time": 0
  },
  "gate_color": ["FF0000", "00FF00", "0000FF", "FFFF00", "FF00FF", "00FFFF", "FFFFFF", "000000"],
  "gate_material": ["PLA", "ABS", "PETG", "TPU", "PLA", "ABS", "", ""],
  "gate_temp": [200, 240, 230, 220, 200, 240, 0, 0],
  "active_gate": ["ready", "ready", "empty", "ready", "ready", "empty", "empty", "empty"],
  "spool_id": [1, 2, 3, 4, 5, 6, 7, 8],
  "selected_gate": 0,
  "endless_spool": false,
  "num_gates": 8,
  "num_devices": 2,
  "devices": [
    {
      "device_id": "mac_001a2b3c",
      "connection_status": "connected",
      "health": {...}
    },
    {
      "device_id": "mac_00aabbcc",
      "connection_status": "connected",
      "health": {...}
    }
  ]
}
```

##### POST /printer/ace/device/rename
**Description**: Rename an ACE device (cosmetic only)

**Request**:
```json
{
  "device_id": "mac_001a2b3c",
  "name": "Filament Tower Left"
}
```

##### POST /printer/ace/device/disconnect
**Description**: Safely disconnect a specific ACE device

**Request**:
```json
{
  "device_id": "mac_001a2b3c"
}
```

### 2. Implementation in ace.py

#### New Methods in AceManager

```python
class AceManager:
    # ... existing code ...

    def get_device_list(self):
        """Get list of all ACE devices with status"""
        devices = []
        for dev in self.ace_devices:
            devices.append({
                'device_id': dev.get('device_id'),
                'name': dev.get('name', f"ACE Unit {dev['gate_offset']//4 + 1}"),
                'port': dev['port'],
                'model': dev.get('model', 'Unknown'),
                'firmware': dev.get('firmware', 'Unknown'),
                'connection_status': 'connected' if dev['instance']._connected else 'disconnected',
                'gate_offset': dev['gate_offset'],
                'num_gates': 4,
                'gates': list(range(dev['gate_offset'], dev['gate_offset'] + 4)),
                'last_seen': dev.get('last_seen', 0),
                'uptime': dev['instance'].get_uptime() if hasattr(dev['instance'], 'get_uptime') else 0,
                'health': dev['instance'].get_health_stats() if hasattr(dev['instance'], 'get_health_stats') else {}
            })

        return {
            'devices': devices,
            'total_gates': self.total_gates,
            'auto_detect_enabled': True,
            'device_map_file': self.device_mapper.config_path
        }

    def scan_devices(self, rescan=True, update_map=True):
        """Manually trigger device scan"""
        if not rescan:
            return self.get_device_list()

        # Re-run auto-detection
        discovered = AceDeviceDiscovery.find_ace_devices()
        new_devices = []

        for dev_info in discovered:
            port = dev_info['port']
            ace_info = AceDeviceDiscovery.probe_ace_device(port)

            if ace_info:
                device_id = ace_info['device_id']
                # Check if this is a new device
                if device_id not in [d.get('device_id') for d in self.ace_devices]:
                    new_devices.append(device_id)
                    logging.info(f"Found new ACE device: {device_id}")

        if update_map and new_devices:
            # Update device map and log
            self.device_mapper.save()

        return {
            'status': 'success',
            'devices_found': len(discovered),
            'new_devices': len(new_devices),
            'devices': self.get_device_list()
        }

    def reorder_gates(self, device_order):
        """Reorder gate assignments for devices"""
        # Validate new order
        device_ids = [d['device_id'] for d in device_order]
        current_ids = [d.get('device_id') for d in self.ace_devices]

        if set(device_ids) != set(current_ids):
            raise Exception("Device order must include all current devices")

        # Update gate offsets in device map
        for order_info in device_order:
            device_id = order_info['device_id']
            new_offset = order_info['gate_offset']
            self.device_mapper.update_device(device_id, None, new_offset)

        self.device_mapper.save()

        return {
            'status': 'success',
            'message': 'Gate assignments updated. Restart required.',
            'restart_required': True
        }
```

#### GCode Commands for Web UI

```python
# Add new gcode commands for web UI integration
gcode.register_command(
    'ACE_SCAN_DEVICES',
    self.cmd_ACE_SCAN_DEVICES,
    desc='Scan for ACE devices')

gcode.register_command(
    'ACE_LIST_DEVICES',
    self.cmd_ACE_LIST_DEVICES,
    desc='List all ACE devices')

def cmd_ACE_SCAN_DEVICES(self, gcmd):
    """Scan for ACE devices and report findings"""
    result = self.scan_devices(rescan=True, update_map=True)

    self.gcode.respond_info(f"=== ACE Device Scan ===")
    self.gcode.respond_info(f"Found {result['devices_found']} devices")
    self.gcode.respond_info(f"New devices: {result['new_devices']}")

    for dev in result['devices']['devices']:
        self.gcode.respond_info(
            f"  {dev['name']}: {dev['model']} @ {dev['port']} "
            f"(Gates {dev['gates'][0]}-{dev['gates'][-1]})"
        )

def cmd_ACE_LIST_DEVICES(self, gcmd):
    """List all ACE devices"""
    devices = self.get_device_list()

    self.gcode.respond_info(f"=== ACE Devices ({devices['total_gates']} gates) ===")

    for dev in devices['devices']:
        status_icon = "✓" if dev['connection_status'] == 'connected' else "✗"
        self.gcode.respond_info(
            f"{status_icon} {dev['name']}: {dev['model']} v{dev['firmware']}"
        )
        self.gcode.respond_info(f"   Port: {dev['port']}")
        self.gcode.respond_info(f"   Gates: {dev['gates'][0]}-{dev['gates'][-1]}")
        self.gcode.respond_info(f"   Status: {dev['connection_status']}")
```

## Web UI Components (Shared Design Language)

### 1. ACE Manager Dashboard Card

**Location**: Mainsail/Fluidd Dashboard

**Features**:
- Overview of all ACE devices
- Quick gate status at a glance
- Device health indicators
- Quick actions (scan, configure)

**Visual Mockup**:
```
┌─────────────────────────────────────────────────────────┐
│ ACE Manager                            [Scan] [Configure]│
├─────────────────────────────────────────────────────────┤
│ 8 Gates │ 2 Devices │ Auto-Detect: ON                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│ ┌──────────────────────────┐ ┌──────────────────────────┐│
│ │ ✓ ACE Unit 1             │ │ ✓ ACE Unit 2             ││
│ │ ACE PRO v2.1.0           │ │ ACE PRO v2.1.0           ││
│ │ /dev/ttyACM0             │ │ /dev/ttyACM1             ││
│ │                          │ │                          ││
│ │ Gates 0-3   [Configure]  │ │ Gates 4-7   [Configure]  ││
│ │ ┌──┬──┬──┬──┐            │ │ ┌──┬──┬──┬──┐            ││
│ │ │●0│●1│ 2│●3│            │ │ │●4│ 5│ 6│●7│            ││
│ │ └──┴──┴──┴──┘            │ │ └──┴──┴──┴──┘            ││
│ │ Resp: 45ms │ Errors: 0   │ │ Resp: 42ms │ Errors: 0   ││
│ └──────────────────────────┘ └──────────────────────────┘│
│                                                           │
│ Legend: ● Ready │ ○ Empty │ ◐ Partial                    │
└─────────────────────────────────────────────────────────┘
```

### 2. Gate Configuration Panel

**Location**: Dedicated ACE configuration page

**Features**:
- Visual gate grid with color swatches
- Material/color assignment
- Drag-to-reorder gates
- Bulk operations

**Component Structure**:
```vue
<template>
  <v-container>
    <!-- Header -->
    <v-row>
      <v-col>
        <h2>ACE Gate Configuration</h2>
        <p>8 gates across 2 devices</p>
      </v-col>
      <v-col align="right">
        <v-btn @click="scanDevices">Scan Devices</v-btn>
        <v-btn @click="saveConfig">Save</v-btn>
      </v-col>
    </v-row>

    <!-- Gate Grid -->
    <v-row>
      <v-col
        v-for="gate in gates"
        :key="gate.id"
        cols="12" md="6" lg="3"
      >
        <gate-card
          :gate="gate"
          @update="updateGate"
          @select="selectGate"
          :selected="selectedGate === gate.id"
        />
      </v-col>
    </v-row>

    <!-- Selected Gate Editor -->
    <v-row v-if="selectedGate !== null">
      <v-col>
        <gate-editor
          :gate="gates[selectedGate]"
          @update="updateGate"
        />
      </v-col>
    </v-row>

    <!-- Device Management -->
    <v-row>
      <v-col>
        <device-list
          :devices="devices"
          @reorder="reorderDevices"
        />
      </v-col>
    </v-row>
  </v-container>
</template>

<script>
export default {
  data() {
    return {
      gates: [],
      devices: [],
      selectedGate: null
    }
  },
  methods: {
    async loadGates() {
      const response = await this.$http.get('/printer/ace/status')
      this.gates = this.buildGateList(response.data)
    },
    async scanDevices() {
      await this.$http.post('/printer/ace/scan')
      await this.loadGates()
      this.showNotification('Devices scanned successfully')
    },
    async updateGate(gateId, updates) {
      await this.$http.post(`/printer/gcode/script?script=ACE_GATE_MAP GATE=${gateId} COLOR=${updates.color} TYPE=${updates.material}`)
      this.gates[gateId] = {...this.gates[gateId], ...updates}
    }
  }
}
</script>
```

### 3. Gate Card Component

**Reusable component for gate display**

```vue
<template>
  <v-card
    :class="cardClass"
    @click="$emit('select', gate.id)"
    elevation="2"
  >
    <!-- Color Indicator Bar -->
    <div
      class="color-bar"
      :style="{backgroundColor: `#${gate.color}`}"
    />

    <!-- Gate Content -->
    <v-card-text>
      <!-- Gate Number & Status -->
      <div class="d-flex justify-space-between align-center mb-2">
        <span class="text-h6">T{{ gate.id }}</span>
        <v-chip
          :color="statusColor"
          small
        >
          {{ gate.status }}
        </v-chip>
      </div>

      <!-- Spool Icon -->
      <div class="spool-icon text-center my-3">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <!-- Outer ring -->
          <circle
            cx="40" cy="40" r="35"
            :fill="`#${gate.color}`"
            stroke="white" stroke-width="2"
          />
          <!-- Inner hole -->
          <circle
            cx="40" cy="40" r="15"
            fill="#1E1E1E"
            stroke="white" stroke-width="2"
          />
          <!-- Gate number -->
          <text
            x="40" y="48"
            text-anchor="middle"
            fill="white"
            font-size="20"
            font-weight="bold"
          >
            {{ gate.id }}
          </text>
        </svg>
      </div>

      <!-- Material Info -->
      <div class="text-center">
        <div class="text-subtitle-1 font-weight-bold">
          {{ gate.material || 'Empty' }}
        </div>
        <div class="text-caption">
          {{ gate.temp }}°C
        </div>
      </div>
    </v-card-text>

    <!-- Actions -->
    <v-card-actions>
      <v-btn
        text small
        @click.stop="$emit('edit', gate.id)"
      >
        Edit
      </v-btn>
      <v-spacer />
      <v-btn
        text small color="primary"
        @click.stop="loadGate"
        :disabled="gate.status === 'empty'"
      >
        Load
      </v-btn>
    </v-card-actions>
  </v-card>
</template>

<script>
export default {
  props: {
    gate: Object,
    selected: Boolean
  },
  computed: {
    cardClass() {
      return {
        'gate-card': true,
        'gate-card--selected': this.selected,
        'gate-card--empty': this.gate.status === 'empty',
        'gate-card--ready': this.gate.status === 'ready'
      }
    },
    statusColor() {
      const colors = {
        'ready': 'success',
        'empty': 'grey',
        'loading': 'warning',
        'error': 'error'
      }
      return colors[this.gate.status] || 'grey'
    }
  },
  methods: {
    loadGate() {
      this.$socket.sendGcode(`T${this.gate.id}`)
    }
  }
}
</script>

<style scoped>
.gate-card {
  cursor: pointer;
  transition: all 0.2s;
  border: 2px solid transparent;
}

.gate-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.gate-card--selected {
  border-color: var(--v-primary-base);
}

.gate-card--empty {
  opacity: 0.6;
}

.color-bar {
  height: 4px;
  width: 100%;
  border-radius: 4px 4px 0 0;
}

.spool-icon {
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
```

### 4. Device Reorder Dialog

**Drag-and-drop interface for reordering devices**

```vue
<template>
  <v-dialog v-model="dialog" max-width="600">
    <template v-slot:activator="{ on }">
      <v-btn v-on="on">Reorder Devices</v-btn>
    </template>

    <v-card>
      <v-card-title>Reorder ACE Devices</v-card-title>

      <v-card-text>
        <p class="text-caption">
          Drag devices to change gate assignments. Changes require a restart.
        </p>

        <draggable
          v-model="orderedDevices"
          @end="updateOrder"
          handle=".drag-handle"
        >
          <v-list-item
            v-for="(device, index) in orderedDevices"
            :key="device.device_id"
            class="device-item"
          >
            <v-list-item-avatar>
              <v-icon class="drag-handle">mdi-drag</v-icon>
            </v-list-item-avatar>

            <v-list-item-content>
              <v-list-item-title>
                {{ device.name }}
              </v-list-item-title>
              <v-list-item-subtitle>
                Gates {{ index * 4 }}-{{ index * 4 + 3 }}
              </v-list-item-subtitle>
            </v-list-item-content>

            <v-list-item-action>
              <v-chip small>{{ device.model }}</v-chip>
            </v-list-item-action>
          </v-list-item>
        </draggable>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn text @click="dialog = false">Cancel</v-btn>
        <v-btn
          color="primary"
          @click="applyReorder"
          :loading="saving"
        >
          Apply & Restart
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script>
import draggable from 'vuedraggable'

export default {
  components: { draggable },
  props: {
    devices: Array
  },
  data() {
    return {
      dialog: false,
      orderedDevices: [],
      saving: false
    }
  },
  watch: {
    devices: {
      immediate: true,
      handler(devices) {
        this.orderedDevices = [...devices]
      }
    }
  },
  methods: {
    updateOrder() {
      // Update gate offsets based on order
      this.orderedDevices = this.orderedDevices.map((dev, index) => ({
        ...dev,
        gate_offset: index * 4
      }))
    },
    async applyReorder() {
      this.saving = true

      const deviceOrder = this.orderedDevices.map(dev => ({
        device_id: dev.device_id,
        gate_offset: dev.gate_offset
      }))

      try {
        await this.$http.post('/printer/ace/reorder', { device_order: deviceOrder })

        // Show restart prompt
        this.$confirm(
          'Device order updated. Restart Klipper to apply changes?',
          'Restart Required',
          {
            confirmText: 'Restart Now',
            cancelText: 'Restart Later'
          }
        ).then(() => {
          this.$socket.sendGcode('FIRMWARE_RESTART')
        })

        this.dialog = false
      } catch (error) {
        this.$toast.error(`Failed to reorder devices: ${error.message}`)
      } finally {
        this.saving = false
      }
    }
  }
}
</script>
```

### 5. Setup Wizard

**First-time setup wizard for ACE system**

```vue
<template>
  <v-stepper v-model="step">
    <!-- Step 1: Detection -->
    <v-stepper-step :complete="step > 1" step="1">
      Detect Devices
    </v-stepper-step>

    <v-stepper-content step="1">
      <v-card>
        <v-card-text>
          <h3>Detecting ACE Devices...</h3>
          <v-progress-linear
            v-if="scanning"
            indeterminate
          />
          <v-list v-else>
            <v-list-item
              v-for="device in detectedDevices"
              :key="device.device_id"
            >
              <v-list-item-icon>
                <v-icon color="success">mdi-check-circle</v-icon>
              </v-list-item-icon>
              <v-list-item-content>
                <v-list-item-title>
                  {{ device.model }} v{{ device.firmware }}
                </v-list-item-title>
                <v-list-item-subtitle>
                  {{ device.port }}
                </v-list-item-subtitle>
              </v-list-item-content>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions>
          <v-btn @click="scanDevices">Scan Again</v-btn>
          <v-spacer />
          <v-btn
            color="primary"
            @click="step = 2"
            :disabled="detectedDevices.length === 0"
          >
            Continue
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-stepper-content>

    <!-- Step 2: Sensor Configuration -->
    <v-stepper-step :complete="step > 2" step="2">
      Configure Sensors
    </v-stepper-step>

    <v-stepper-content step="2">
      <v-card>
        <v-card-text>
          <h3>Sensor Pin Configuration</h3>
          <v-text-field
            v-model="config.extruder_sensor_pin"
            label="Extruder Sensor Pin"
            hint="e.g., ^EBBCan:PB9"
          />
          <v-text-field
            v-model="config.toolhead_sensor_pin"
            label="Toolhead Sensor Pin (optional)"
            hint="e.g., EBBCan:PB8"
          />
        </v-card-text>
        <v-card-actions>
          <v-btn @click="step = 1">Back</v-btn>
          <v-spacer />
          <v-btn color="primary" @click="step = 3">Continue</v-btn>
        </v-card-actions>
      </v-card>
    </v-stepper-content>

    <!-- Step 3: Test & Finish -->
    <v-stepper-step step="3">
      Test & Finish
    </v-stepper-step>

    <v-stepper-content step="3">
      <v-card>
        <v-card-text>
          <h3>Configuration Complete!</h3>
          <p>
            Found {{ detectedDevices.length }} ACE device(s) with
            {{ detectedDevices.length * 4 }} total gates.
          </p>
          <v-alert type="info">
            Your configuration has been saved. Click "Finish" to restart Klipper.
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-btn @click="step = 2">Back</v-btn>
          <v-spacer />
          <v-btn
            color="success"
            @click="finishSetup"
            :loading="finishing"
          >
            Finish & Restart
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-stepper-content>
  </v-stepper>
</template>

<script>
export default {
  data() {
    return {
      step: 1,
      scanning: false,
      finishing: false,
      detectedDevices: [],
      config: {
        extruder_sensor_pin: '^EBBCan:PB9',
        toolhead_sensor_pin: 'EBBCan:PB8'
      }
    }
  },
  mounted() {
    this.scanDevices()
  },
  methods: {
    async scanDevices() {
      this.scanning = true
      try {
        const response = await this.$http.post('/printer/ace/scan')
        this.detectedDevices = response.data.devices.devices || []
      } catch (error) {
        this.$toast.error('Failed to scan for devices')
      } finally {
        this.scanning = false
      }
    },
    async finishSetup() {
      this.finishing = true
      try {
        // Save config via GCode
        await this.$socket.sendGcode(`SAVE_CONFIG`)

        // Wait a moment then restart
        setTimeout(() => {
          this.$socket.sendGcode('FIRMWARE_RESTART')
        }, 1000)
      } catch (error) {
        this.$toast.error('Setup failed')
        this.finishing = false
      }
    }
  }
}
</script>
```

## Integration Points

### Mainsail
- Add ACE panel to navigation sidebar
- Register ACE Manager dashboard widget
- Add ACE configuration to settings page
- Subscribe to ACE status updates via websocket

### Fluidd
- Add ACE section to Tools menu
- Create ACE configuration panel
- Implement gate status widget for dashboard
- Subscribe to printer object updates for `ace`

## Data Flow

```
┌──────────────┐      WebSocket      ┌──────────────┐
│  Web Browser │ ◄─────────────────► │  Moonraker   │
└──────────────┘                     └──────────────┘
      │                                      │
      │ REST API                            │
      │ /printer/ace/*                      │ Unix Socket
      ▼                                      ▼
┌──────────────┐                     ┌──────────────┐
│ HTTP Requests│                     │   Klippy     │
└──────────────┘                     └──────────────┘
                                             │
                                             │
                                             ▼
                                     ┌──────────────┐
                                     │  AceManager  │
                                     └──────────────┘
                                             │
                                   ┌─────────┼─────────┐
                                   ▼         ▼         ▼
                              ┌────────┬────────┬────────┐
                              │ ACE #1 │ ACE #2 │ ACE #3 │
                              └────────┴────────┴────────┘
```

## Testing

### Unit Tests
- API endpoint responses
- Device list serialization
- Gate reordering logic

### Integration Tests
- Scan devices from web UI
- Update gate configuration
- Reorder devices
- Monitor status updates

### UI Tests
- Gate card rendering
- Drag-and-drop reordering
- Configuration wizard flow
- Responsive design on mobile

## Performance Considerations

1. **Websocket Updates**: Only send updates when gate status changes
2. **Polling**: Dashboard polls ACE status every 2 seconds
3. **Caching**: Cache device list, only refresh on scan
4. **Lazy Loading**: Load gate images/icons on demand

## Browser Compatibility

- Chrome/Edge 90+
- Firefox 88+
- Safari 14+
- Mobile browsers supported

## Accessibility

- Keyboard navigation for all controls
- Screen reader labels for status indicators
- High contrast mode support
- ARIA labels for interactive elements
