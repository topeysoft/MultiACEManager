# Mainsail UI Specification for ACE Manager

## Overview
Comprehensive UI/UX design for ACE multi-device management in Mainsail, providing zero-config device management, visual gate status, and intuitive control.

## Design Philosophy
- **Zero-config first**: Auto-detection should be the default, manual config optional
- **Visual feedback**: Clear status indicators for all devices and gates
- **Touch-friendly**: Large touch targets for tablet/phone use
- **Information hierarchy**: Most important info at a glance, details on demand
- **Consistency**: Match Mainsail's existing design language

---

## 1. Dashboard Widget

### Location
Main dashboard, suggested default position: Below temperature card

### Widget Sizes
- **Small**: 2 columns × 2 rows - Quick status only
- **Medium**: 4 columns × 2 rows - Status + quick controls (default)
- **Large**: 4 columns × 3 rows - Full gate grid

### Small Widget Layout (2×2)
```
┌─────────────────────────────────────┐
│ ACE Manager              [Settings] │
│ ● 8 Gates │ 2 Devices │ Ready       │
├─────────────────────────────────────┤
│ Active: T3 (PLA #FF0000)            │
│ Temp: 25°C │ Dryer: Off             │
└─────────────────────────────────────┘
```

**Components:**
- Header with title and settings button
- Status line: Total gates, device count, overall status
- Active gate display with color swatch
- Environmental info: temp, dryer status

### Medium Widget Layout (4×2)
```
┌─────────────────────────────────────────────────────────────────┐
│ ACE Manager                                         [Settings]  │
│ ● 8 Gates │ 2 Devices │ Auto-Detect: ON                         │
├─────────────────────────────────────────────────────────────────┤
│ Gates:  ●0  ●1   2  ●3  ●4   5   6  ●7                          │
│         PLA ABS --- PETG PLA --- --- TPU                        │
├─────────────────────────────────────────────────────────────────┤
│ [📦 Select Gate ▼] [🔄 Scan] [⚙️ Configure] [🌡️ Dryer]         │
└─────────────────────────────────────────────────────────────────┘
```

**Components:**
- Gate status grid: 8 inline status indicators
- Material labels below each gate
- Action buttons: Gate selector dropdown, scan, configure, dryer

### Large Widget Layout (4×3)
```
┌─────────────────────────────────────────────────────────────────┐
│ ACE Manager                                         [Settings]  │
│ ● 8 Gates │ 2 Devices │ Auto-Detect: ON │ Temp: 25°C            │
├─────────────────────────────────────────────────────────────────┤
│ ACE Unit 1 (Gates 0-3)                    ✓ Connected  45ms     │
│ ┌──────┬──────┬──────┬──────┐                                   │
│ │  ●0  │  ●1  │  ○2  │  ●3  │                                   │
│ │ PLA  │ ABS  │ ---  │ PETG │                                   │
│ │ 🔴  │ 🟡  │ ⚪  │ 🔵  │                                   │
│ └──────┴──────┴──────┴──────┘                                   │
│                                                                  │
│ ACE Unit 2 (Gates 4-7)                    ✓ Connected  42ms     │
│ ┌──────┬──────┬──────┬──────┐                                   │
│ │  ●4  │  ○5  │  ○6  │  ●7  │                                   │
│ │ PLA  │ ---  │ ---  │ TPU  │                                   │
│ │ 🔴  │ ⚪  │ ⚪  │ 🟣  │                                   │
│ └──────┴──────┴──────┴──────┘                                   │
├─────────────────────────────────────────────────────────────────┤
│ [📦 Select Gate ▼] [🔄 Scan] [⚙️ Configure] [🌡️ Dryer]         │
└─────────────────────────────────────────────────────────────────┘

Legend: ● Ready │ ○ Empty │ ◐ Partial
```

**Components:**
- Device cards with connection status and response time
- 4-gate grids per device with visual indicators
- Color swatches for each gate
- Legend for status indicators

### Component Specifications

#### Gate Status Indicator
```vue
<template>
  <div class="gate-indicator" :class="statusClass">
    <div class="gate-number">{{ gate }}</div>
    <div class="gate-status-icon" :style="iconStyle">
      {{ statusIcon }}
    </div>
  </div>
</template>

<style scoped>
.gate-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 0.875rem;
}

.gate-indicator.ready {
  background: rgba(76, 175, 80, 0.1);
  border: 1px solid #4CAF50;
}

.gate-indicator.empty {
  background: rgba(158, 158, 158, 0.1);
  border: 1px solid #9E9E9E;
  opacity: 0.6;
}

.gate-number {
  font-weight: 600;
}

.gate-status-icon {
  font-size: 1rem;
}
</style>
```

---

## 2. ACE Configuration Page

### Navigation
**Main Menu → Settings → ACE Manager**

### Page Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ← Settings                ACE Manager                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ┌──── Device Configuration ─────────────────────────────────┐  │
│ │ Auto-Detect Devices: ⚫ON  [🔄 Scan Now]                   │  │
│ │                                                             │  │
│ │ Devices Found: 2                                            │  │
│ │ Total Gates: 8 (0-7)                                        │  │
│ │ Device Map: /config/ace_device_map.cfg ✓ Saved             │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌──── Connected Devices ────────────────────────────────────┐  │
│ │                                                             │  │
│ │ ┌─ ACE Unit 1 ─────────────────────────────────────────┐  │  │
│ │ │ ✓ Connected  │  ACE PRO v2.1.0  │  /dev/ttyACM0      │  │  │
│ │ │ Device ID: mac_001a2b3c                                │  │  │
│ │ │ Gates: 0-3                                             │  │  │
│ │ │ Health: Excellent ● Avg Response: 45ms                │  │  │
│ │ │                                                         │  │  │
│ │ │ [📊 Health Stats] [🔧 Configure] [↕️ Reorder]         │  │  │
│ │ └─────────────────────────────────────────────────────────┘  │  │
│ │                                                             │  │
│ │ ┌─ ACE Unit 2 ─────────────────────────────────────────┐  │  │
│ │ │ ✓ Connected  │  ACE PRO v2.1.0  │  /dev/ttyACM1      │  │  │
│ │ │ Device ID: mac_00aabbcc                                │  │  │
│ │ │ Gates: 4-7                                             │  │  │
│ │ │ Health: Good ● Avg Response: 42ms                     │  │  │
│ │ │                                                         │  │  │
│ │ │ [📊 Health Stats] [🔧 Configure] [↕️ Reorder]         │  │  │
│ │ └─────────────────────────────────────────────────────────┘  │  │
│ │                                                             │  │
│ │ [+ Add Device Manually]                                     │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌──── Gate Configuration ───────────────────────────────────┐  │
│ │                                                             │  │
│ │ ┌──┬──┬──┬──┬──┬──┬──┬──┐                                  │  │
│ │ │T0│T1│T2│T3│T4│T5│T6│T7│                                  │  │
│ │ └──┴──┴──┴──┴──┴──┴──┴──┘                                  │  │
│ │                                                             │  │
│ │ (Click a gate to configure)                                 │  │
│ └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌──── Advanced Settings ────────────────────────────────────┐  │
│ │ Sensor Configuration                                        │  │
│ │ • Extruder Sensor Pin: ^EBBCan:PB9                         │  │
│ │ • Toolhead Sensor Pin: EBBCan:PB8                          │  │
│ │                                                             │  │
│ │ Speed Settings                                              │  │
│ │ • Feed Speed: 80 mm/s                                      │  │
│ │ • Retract Speed: 80 mm/s                                   │  │
│ │ • Extruder Move Speed: 10 mm/s                             │  │
│ │                                                             │  │
│ │ [Edit Configuration File]                                   │  │
│ └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Device Card Component

```vue
<template>
  <v-expansion-panel>
    <v-expansion-panel-header>
      <div class="device-header">
        <v-icon :color="connectionColor" class="mr-2">
          {{ connectionIcon }}
        </v-icon>

        <div class="device-info">
          <div class="device-name">
            {{ device.name }}
            <v-chip x-small :color="healthColor" class="ml-2">
              {{ device.health.status }}
            </v-chip>
          </div>

          <div class="device-details">
            {{ device.model }} v{{ device.firmware }} │
            {{ device.port }} │
            Gates {{ device.gates[0] }}-{{ device.gates[device.gates.length - 1] }}
          </div>
        </div>

        <div class="device-stats ml-auto">
          <div class="stat-item">
            <span class="stat-label">Avg Response</span>
            <span class="stat-value">{{ device.health.avg_response_time_ms }}ms</span>
          </div>

          <div class="stat-item">
            <span class="stat-label">Success Rate</span>
            <span class="stat-value">{{ (device.health.success_rate * 100).toFixed(1) }}%</span>
          </div>
        </div>
      </div>
    </v-expansion-panel-header>

    <v-expansion-panel-content>
      <!-- Device details and controls -->
      <v-row>
        <v-col cols="12" md="6">
          <div class="detail-section">
            <h4>Device Information</h4>
            <v-simple-table dense>
              <tbody>
                <tr>
                  <td>Device ID</td>
                  <td><code>{{ device.device_id }}</code></td>
                </tr>
                <tr>
                  <td>Model</td>
                  <td>{{ device.model }}</td>
                </tr>
                <tr>
                  <td>Firmware</td>
                  <td>{{ device.firmware }}</td>
                </tr>
                <tr>
                  <td>Port</td>
                  <td><code>{{ device.port }}</code></td>
                </tr>
                <tr>
                  <td>Uptime</td>
                  <td>{{ formatUptime(device.uptime) }}</td>
                </tr>
              </tbody>
            </v-simple-table>
          </div>
        </v-col>

        <v-col cols="12" md="6">
          <div class="detail-section">
            <h4>Health Metrics</h4>
            <v-simple-table dense>
              <tbody>
                <tr>
                  <td>Status</td>
                  <td>
                    <v-chip x-small :color="healthColor">
                      {{ device.health.status }}
                    </v-chip>
                  </td>
                </tr>
                <tr>
                  <td>Total Requests</td>
                  <td>{{ device.health.total_requests }}</td>
                </tr>
                <tr>
                  <td>Success Rate</td>
                  <td>{{ (device.health.success_rate * 100).toFixed(2) }}%</td>
                </tr>
                <tr>
                  <td>Avg Response Time</td>
                  <td>{{ device.health.avg_response_time_ms.toFixed(1) }}ms</td>
                </tr>
                <tr>
                  <td>P95 Response Time</td>
                  <td>{{ device.health.p95_response_time_ms.toFixed(1) }}ms</td>
                </tr>
                <tr>
                  <td>Error Count</td>
                  <td>{{ device.health.error_count }}</td>
                </tr>
              </tbody>
            </v-simple-table>
          </div>
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <v-row>
        <v-col>
          <v-btn text @click="showHealthChart">
            <v-icon left>mdi-chart-line</v-icon>
            Response Time Chart
          </v-btn>

          <v-btn text @click="runDiagnostics">
            <v-icon left>mdi-stethoscope</v-icon>
            Run Diagnostics
          </v-btn>

          <v-btn text color="error" @click="disconnectDevice">
            <v-icon left>mdi-connection</v-icon>
            Disconnect
          </v-btn>
        </v-col>
      </v-row>
    </v-expansion-panel-content>
  </v-expansion-panel>
</template>

<script>
export default {
  props: {
    device: {
      type: Object,
      required: true
    }
  },
  computed: {
    connectionColor() {
      return this.device.connection_status === 'connected' ? 'success' : 'error'
    },
    connectionIcon() {
      return this.device.connection_status === 'connected'
        ? 'mdi-check-circle'
        : 'mdi-close-circle'
    },
    healthColor() {
      const colors = {
        excellent: 'success',
        good: 'info',
        fair: 'warning',
        poor: 'error'
      }
      return colors[this.device.health.status] || 'grey'
    }
  },
  methods: {
    formatUptime(seconds) {
      const hours = Math.floor(seconds / 3600)
      const minutes = Math.floor((seconds % 3600) / 60)
      return `${hours}h ${minutes}m`
    },
    showHealthChart() {
      this.$emit('show-chart', this.device.device_id)
    },
    runDiagnostics() {
      this.$emit('run-diagnostics', this.device.device_id)
    },
    disconnectDevice() {
      this.$emit('disconnect', this.device.device_id)
    }
  }
}
</script>
```

---

## 3. Gate Configuration Dialog

### Dialog Layout

```
┌────────────────────────────────────────────────────────────┐
│ Configure Gate 3                                      [×]   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌────────── Preview ──────────┐                           │
│  │                              │                           │
│  │         ┌─────────┐          │                           │
│  │         │         │          │                           │
│  │         │   🔵    │          │                           │
│  │         │    3    │          │                           │
│  │         │         │          │                           │
│  │         └─────────┘          │                           │
│  │          PETG                │                           │
│  │          230°C               │                           │
│  └──────────────────────────────┘                           │
│                                                             │
│  Material:                                                  │
│  ┌───┬───┬───┬───┬───┬───┬───┬───┐                         │
│  │PLA│ABS│ASA│PETG│TPU│ PA│ PC│PVA│                         │
│  └───┴───┴───┴─▼─┴───┴───┴───┴───┘                         │
│                                                             │
│  Color:                                                     │
│  ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐         │
│  │🔴│🟠│🟡│🟢│🔵│🟣│⚫│⚪│🟤│···│                         │
│  └──┴──┴──┴──┴▼─┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘         │
│                                                             │
│  Temperature: [230] °C  [Slider: 180─────●───280]          │
│                                                             │
│  Custom Name (optional): [PETG Blue               ]        │
│                                                             │
│  Spool ID: [3      ]  Weight: [1000    ] g                 │
│                                                             │
│ ┌─ Advanced ─────────────────────────────────────────────┐ │
│ │ Endless Spool Group: [None ▼]                          │ │
│ │ Feed Speed Override: [─]                               │ │
│ │ Retract Speed Override: [─]                            │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                             │
├────────────────────────────────────────────────────────────┤
│                    [Cancel]  [Apply]  [Apply & Load]       │
└────────────────────────────────────────────────────────────┘
```

### Color Picker Component

```vue
<template>
  <div class="color-picker">
    <div class="color-palette">
      <div
        v-for="color in colorPalette"
        :key="color.hex"
        class="color-swatch"
        :class="{ selected: selectedColor === color.hex }"
        :style="{ backgroundColor: `#${color.hex}` }"
        @click="selectColor(color.hex)"
      >
        <v-icon v-if="selectedColor === color.hex" small color="white">
          mdi-check
        </v-icon>
      </div>
    </div>

    <v-text-field
      v-model="customColor"
      label="Custom Hex Color"
      prefix="#"
      maxlength="6"
      @input="onCustomColorInput"
      hint="Enter 6-digit hex code"
    />
  </div>
</template>

<script>
export default {
  props: {
    value: String
  },
  data() {
    return {
      selectedColor: this.value,
      customColor: this.value,
      colorPalette: [
        { name: 'Red', hex: 'FF0000' },
        { name: 'Orange', hex: 'FF8000' },
        { name: 'Yellow', hex: 'FFFF00' },
        { name: 'Lime', hex: '80FF00' },
        { name: 'Green', hex: '00FF00' },
        { name: 'Cyan', hex: '00FFFF' },
        { name: 'Blue', hex: '0000FF' },
        { name: 'Purple', hex: '8000FF' },
        { name: 'Magenta', hex: 'FF00FF' },
        { name: 'Pink', hex: 'FF0080' },
        { name: 'White', hex: 'FFFFFF' },
        { name: 'Black', hex: '000000' },
        { name: 'Gray', hex: '808080' },
        { name: 'Brown', hex: '8B4513' },
        { name: 'Silver', hex: 'C0C0C0' },
        { name: 'Gold', hex: 'FFD700' }
      ]
    }
  },
  methods: {
    selectColor(hex) {
      this.selectedColor = hex
      this.customColor = hex
      this.$emit('input', hex)
    },
    onCustomColorInput(value) {
      // Validate hex color
      if (/^[0-9A-Fa-f]{6}$/.test(value)) {
        this.selectColor(value.toUpperCase())
      }
    }
  }
}
</script>

<style scoped>
.color-palette {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 8px;
  margin-bottom: 16px;
}

.color-swatch {
  aspect-ratio: 1;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.color-swatch:hover {
  transform: scale(1.1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.color-swatch.selected {
  border-color: var(--v-primary-base);
  box-shadow: 0 0 0 3px rgba(var(--v-primary-base), 0.3);
}
</style>
```

---

## 4. Device Reorder Interface

### Drag-and-Drop UI

```
┌────────────────────────────────────────────────────────────┐
│ Reorder ACE Devices                                   [×]   │
├────────────────────────────────────────────────────────────┤
│                                                             │
│ Drag devices to change gate assignments.                   │
│ ⚠️ Changes require Klipper restart.                         │
│                                                             │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ ≡≡ ACE Unit 1                              Gates 0-3   │ │
│ │    ACE PRO v2.1.0  │  /dev/ttyACM0                     │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌────────────────────────────────────────────────────────┐ │
│ │ ≡≡ ACE Unit 2                              Gates 4-7   │ │
│ │    ACE PRO v2.1.0  │  /dev/ttyACM1                     │ │
│ └────────────────────────────────────────────────────────┘ │
│                                                             │
│ Preview:                                                    │
│ T0-T3: ACE Unit 1                                          │
│ T4-T7: ACE Unit 2                                          │
│                                                             │
├────────────────────────────────────────────────────────────┤
│                    [Cancel]  [Apply & Restart Klipper]     │
└────────────────────────────────────────────────────────────┘
```

---

## 5. Setup Wizard

### Wizard Flow

**Step 1: Welcome & Auto-Detect**
```
┌────────────────────────────────────────────────────────────┐
│ ACE Manager Setup Wizard                        Step 1 of 3│
├────────────────────────────────────────────────────────────┤
│                                                             │
│         Welcome to ACE Manager!                            │
│                                                             │
│   Let's detect your ACE devices automatically.             │
│                                                             │
│         ┌──────────────────────────┐                       │
│         │   🔍  Scanning...        │                       │
│         │                          │                       │
│         │   ████████░░░░░░  60%   │                       │
│         └──────────────────────────┘                       │
│                                                             │
│   Found devices:                                            │
│   ✓ ACE PRO v2.1.0 at /dev/ttyACM0                         │
│   ✓ ACE PRO v2.1.0 at /dev/ttyACM1                         │
│                                                             │
├────────────────────────────────────────────────────────────┤
│              [Scan Again]           [Continue →]           │
└────────────────────────────────────────────────────────────┘
```

**Step 2: Sensor Configuration**
```
┌────────────────────────────────────────────────────────────┐
│ ACE Manager Setup Wizard                        Step 2 of 3│
├────────────────────────────────────────────────────────────┤
│                                                             │
│   Configure Sensor Pins                                    │
│                                                             │
│   Extruder Sensor Pin *                                    │
│   [^EBBCan:PB9                                    ]        │
│   ⓘ Pin where filament entry is detected                   │
│                                                             │
│   Toolhead Sensor Pin (optional)                           │
│   [EBBCan:PB8                                     ]        │
│   ⓘ Pin at toolhead for precise filament positioning       │
│                                                             │
│   Would you like to test the sensors?                      │
│   [Test Sensors]                                           │
│                                                             │
├────────────────────────────────────────────────────────────┤
│              [← Back]               [Continue →]           │
└────────────────────────────────────────────────────────────┘
```

**Step 3: Complete**
```
┌────────────────────────────────────────────────────────────┐
│ ACE Manager Setup Wizard                        Step 3 of 3│
├────────────────────────────────────────────────────────────┤
│                                                             │
│          ✓ Setup Complete!                                 │
│                                                             │
│   Configuration Summary:                                    │
│   • 2 ACE devices detected                                 │
│   • 8 total gates (T0-T7)                                  │
│   • Auto-detect enabled                                    │
│   • Device map saved                                       │
│                                                             │
│   Next Steps:                                              │
│   1. Configure filament materials and colors              │
│   2. Test tool changes (T0-T7)                            │
│   3. Start your first multi-material print!               │
│                                                             │
│   Click "Finish" to restart Klipper and activate          │
│   your ACE configuration.                                  │
│                                                             │
├────────────────────────────────────────────────────────────┤
│              [← Back]         [Finish & Restart]           │
└────────────────────────────────────────────────────────────┘
```

---

## Color Scheme

### Status Colors
- **Connected**: `#4CAF50` (Green)
- **Disconnected**: `#F44336` (Red)
- **Warning**: `#FF9800` (Orange)
- **Info**: `#2196F3` (Blue)

### Health Status Colors
- **Excellent**: `#4CAF50` (Green)
- **Good**: `#2196F3` (Blue)
- **Fair**: `#FF9800` (Orange)
- **Poor**: `#F44336` (Red)

### Gate Status Colors
- **Ready**: Green background
- **Empty**: Gray background
- **Loading**: Yellow background
- **Error**: Red background

---

## Responsive Design

### Breakpoints
- **Mobile**: < 600px - Stack all elements vertically
- **Tablet**: 600px - 960px - 2-column layout
- **Desktop**: > 960px - 4-column layout

### Mobile Optimizations
- Touch targets minimum 48×48px
- Larger font sizes for readability
- Simplified gate grid (2 columns max)
- Bottom sheet dialogs instead of modals
- Swipe gestures for gate navigation

---

## Accessibility

### ARIA Labels
- All interactive elements have aria-labels
- Status indicators use aria-live regions
- Color swatches include text labels for screen readers

### Keyboard Navigation
- Tab order follows visual flow
- Enter/Space to activate buttons
- Arrow keys to navigate gate grid
- Escape to close dialogs

### High Contrast Mode
- Borders on all status indicators
- Text labels accompany all color-coded elements
- Focus indicators clearly visible

---

## Performance

### Optimization Strategies
- Virtual scrolling for large gate lists (>16 gates)
- Lazy load device cards
- Debounce live updates (2-second interval)
- Cache gate configuration locally
- Compress websocket messages

### Loading States
- Skeleton screens for initial load
- Progress indicators for scans
- Optimistic UI updates for gate changes

---

## Error Handling

### Error Display
```
┌────────────────────────────────────────┐
│ ⚠️ ACE Connection Error                │
├────────────────────────────────────────┤
│ Failed to connect to ACE Unit 1        │
│                                        │
│ Possible causes:                       │
│ • Device disconnected                  │
│ • USB cable issue                      │
│ • Port permission denied               │
│                                        │
│ [Retry] [Troubleshoot] [Dismiss]      │
└────────────────────────────────────────┘
```

### Troubleshooting Guide Link
All errors include link to troubleshooting documentation

---

This specification provides a complete, production-ready UI design for Mainsail that prioritizes usability, visual clarity, and zero-configuration setup.
