# Fluidd UI Specification for ACE Manager

## Overview
Comprehensive UI/UX design for ACE multi-device management in Fluidd, aligned with Fluidd's minimalist design philosophy while providing powerful device management capabilities.

## Design Philosophy
- **Minimalist**: Clean, uncluttered interface matching Fluidd's aesthetic
- **Information density**: More data in less space compared to Mainsail
- **Performance first**: Lightweight components, fast load times
- **Compact controls**: Efficient use of screen real estate
- **Dark mode optimized**: Designed for Fluidd's dark theme

---

## 1. Dashboard Card

### Location
Dashboard tab, user can add via "+ Add Card" button

### Card Variants

#### Compact Card (Default)
```
┌───────────────────────────────────────────────────┐
│ ACE Manager                              [⚙][↻]  │
├───────────────────────────────────────────────────┤
│ 2 Devices │ 8 Gates │ Auto: ON │ T3 Active       │
│                                                    │
│ 0●  1●  2○  3●  4●  5○  6○  7●                    │
│ PLA ABS --- PETG PLA --- --- TPU                  │
│                                                    │
│ Status: Ready │ Temp: 25°C │ Dryer: Off          │
└───────────────────────────────────────────────────┘
```

**Features:**
- Single-line status summary
- Inline gate status indicators (●=ready, ○=empty)
- Material names below gates
- Environment info footer
- Settings and refresh buttons in header

#### Expanded Card
```
┌───────────────────────────────────────────────────┐
│ ACE Manager                              [⚙][↻]  │
├───────────────────────────────────────────────────┤
│ ACE Unit 1  ✓ 45ms  │  /dev/ttyACM0  │  T0-T3   │
│ ┌─────┬─────┬─────┬─────┐                        │
│ │ ●0  │ ●1  │ ○2  │ ●3  │                        │
│ │ PLA │ ABS │ --- │PETG │                        │
│ │ 🔴 │ 🟡 │ ⚪ │ 🔵 │                        │
│ └─────┴─────┴─────┴─────┘                        │
│                                                    │
│ ACE Unit 2  ✓ 42ms  │  /dev/ttyACM1  │  T4-T7   │
│ ┌─────┬─────┬─────┬─────┐                        │
│ │ ●4  │ ○5  │ ○6  │ ●7  │                        │
│ │ PLA │ --- │ --- │ TPU │                        │
│ │ 🔴 │ ⚪ │ ⚪ │ 🟣 │                        │
│ └─────┴─────┴─────┴─────┘                        │
│                                                    │
│ [Select ▼] [Load] [Unload] [Configure]          │
└───────────────────────────────────────────────────┘
```

**Features:**
- Device-grouped gate display
- Connection status and response time
- Visual color swatches per gate
- Quick action buttons

### Component Code

```vue
<template>
  <v-card>
    <app-card-toolbar
      :title="$t('ACE Manager')"
      :draggable="draggable"
      :layout-path="layoutPath"
    >
      <template #actions>
        <app-btn-collapse-group :collapsed="collapsed" @click="collapsed = !collapsed" />
        <v-btn icon @click="refreshStatus">
          <v-icon small>$refresh</v-icon>
        </v-btn>
        <v-btn icon @click="openSettings">
          <v-icon small>$cog</v-icon>
        </v-btn>
      </template>
    </app-card-toolbar>

    <!-- Compact View -->
    <v-card-text v-if="collapsed" class="py-2">
      <div class="d-flex align-center text-caption mb-1">
        <span>{{ deviceCount }} Devices</span>
        <v-divider vertical class="mx-2" />
        <span>{{ totalGates }} Gates</span>
        <v-divider vertical class="mx-2" />
        <span>Auto: {{ autoDetect ? 'ON' : 'OFF' }}</span>
        <v-divider vertical class="mx-2" />
        <span v-if="activeGate >= 0">T{{ activeGate }} Active</span>
      </div>

      <!-- Gate status inline -->
      <div class="gates-inline">
        <span
          v-for="gate in gates"
          :key="gate.id"
          class="gate-indicator-inline"
          :class="gateStatusClass(gate)"
          @click="selectGate(gate.id)"
        >
          {{ gate.id }}{{ gate.status === 'ready' ? '●' : '○' }}
        </span>
      </div>

      <!-- Material labels -->
      <div class="materials-inline text-caption mt-1">
        <span
          v-for="gate in gates"
          :key="`mat-${gate.id}`"
          class="material-label"
        >
          {{ gate.material || '---' }}
        </span>
      </div>

      <!-- Status footer -->
      <div class="status-footer text-caption mt-2">
        <span>{{ aceStatus }}</span>
        <v-divider vertical class="mx-2" />
        <span>{{ temperature }}°C</span>
        <v-divider vertical class="mx-2" />
        <span>Dryer: {{ dryerStatus }}</span>
      </div>
    </v-card-text>

    <!-- Expanded View -->
    <v-card-text v-else class="py-2">
      <div
        v-for="device in devices"
        :key="device.device_id"
        class="device-section mb-3"
      >
        <!-- Device header -->
        <div class="device-header text-caption d-flex align-center mb-1">
          <span class="font-weight-bold">{{ device.name }}</span>
          <v-icon
            x-small
            :color="device.connection_status === 'connected' ? 'success' : 'error'"
            class="ml-1"
          >
            {{ device.connection_status === 'connected' ? '$checkCircle' : '$alertCircle' }}
          </v-icon>
          <span class="ml-1">{{ device.health.avg_response_time_ms }}ms</span>
          <v-divider vertical class="mx-2" />
          <span>{{ device.port }}</span>
          <v-divider vertical class="mx-2" />
          <span>T{{ device.gates[0] }}-T{{ device.gates[device.gates.length - 1] }}</span>
        </div>

        <!-- Gate grid -->
        <div class="gate-grid">
          <div
            v-for="gateId in device.gates"
            :key="gateId"
            class="gate-cell"
            :class="getGateClass(gateId)"
            @click="selectGate(gateId)"
          >
            <div class="gate-number">
              {{ gateStatus[gateId] === 'ready' ? '●' : '○' }}{{ gateId }}
            </div>
            <div class="gate-material">{{ gateMaterials[gateId] || '---' }}</div>
            <div
              class="gate-color-swatch"
              :style="{ backgroundColor: `#${gateColors[gateId] || 'FFFFFF'}` }"
            />
          </div>
        </div>
      </div>

      <!-- Action buttons -->
      <div class="actions mt-2">
        <v-btn x-small class="mr-1" @click="showGateSelector">
          <v-icon left x-small>$unfoldMoreHorizontal</v-icon>
          Select
        </v-btn>
        <v-btn x-small class="mr-1" @click="loadSelected">
          <v-icon left x-small>$arrowDown</v-icon>
          Load
        </v-btn>
        <v-btn x-small class="mr-1" @click="unloadSelected">
          <v-icon left x-small>$arrowUp</v-icon>
          Unload
        </v-btn>
        <v-btn x-small @click="openConfig">
          <v-icon left x-small>$cog</v-icon>
          Configure
        </v-btn>
      </div>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  data() {
    return {
      collapsed: false,
      devices: [],
      gates: [],
      selectedGate: -1
    }
  },
  computed: {
    deviceCount() {
      return this.devices.length
    },
    totalGates() {
      return this.devices.reduce((sum, d) => sum + d.num_gates, 0)
    },
    autoDetect() {
      return this.$store.state.printer.ace?.auto_detect || false
    },
    activeGate() {
      return this.$store.state.printer.ace?.selected_gate || -1
    },
    aceStatus() {
      return this.$store.state.printer.ace?.status || 'unknown'
    },
    temperature() {
      return this.$store.state.printer.ace?.temp || 0
    },
    dryerStatus() {
      const dryer = this.$store.state.printer.ace?.dryer_status
      return dryer?.status === 'stop' ? 'Off' : 'On'
    }
  }
}
</script>

<style scoped>
.gates-inline {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.gate-indicator-inline {
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.gate-indicator-inline.ready {
  background: rgba(76, 175, 80, 0.2);
}

.gate-indicator-inline.empty {
  background: rgba(158, 158, 158, 0.2);
  opacity: 0.6;
}

.materials-inline {
  display: flex;
  gap: 8px;
}

.material-label {
  min-width: 32px;
  text-align: center;
  font-size: 0.7rem;
}

.gate-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
}

.gate-cell {
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}

.gate-cell:hover {
  border-color: var(--v-primary-base);
  background: rgba(255, 255, 255, 0.05);
}

.gate-cell.selected {
  border-color: var(--v-primary-base);
  border-width: 2px;
}

.gate-number {
  font-weight: 600;
  font-size: 0.875rem;
}

.gate-material {
  font-size: 0.7rem;
  margin-top: 4px;
}

.gate-color-swatch {
  width: 100%;
  height: 4px;
  border-radius: 2px;
  margin-top: 4px;
}

.status-footer {
  display: flex;
  align-items: center;
}

.device-section {
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 4px;
  padding: 8px;
}
</style>
```

---

## 2. Tools Panel Integration

### Location
Tools tab → ACE section

### Panel Layout

```
┌─────────────────────────────────────────────────┐
│ Tools                                            │
├─────────────────────────────────────────────────┤
│                                                  │
│ ▼ ACE Manager                                   │
│                                                  │
│   ┌── Devices ─────────────────────────────┐   │
│   │ Auto-Detect: ●ON   [Scan]              │   │
│   │                                          │   │
│   │ • ACE Unit 1  ✓ Connected  45ms         │   │
│   │   T0-T3  │  /dev/ttyACM0                │   │
│   │                                          │   │
│   │ • ACE Unit 2  ✓ Connected  42ms         │   │
│   │   T4-T7  │  /dev/ttyACM1                │   │
│   │                                          │   │
│   │ Total: 8 gates across 2 devices         │   │
│   └──────────────────────────────────────────┘   │
│                                                  │
│ ▼ Gate Configuration                            │
│                                                  │
│   Selected Gate: [T3 ▼]                         │
│                                                  │
│   Material: [PETG ▼]  Color: [🔵 Select]       │
│   Temp: [230°C]       Spool ID: [3]            │
│                                                  │
│   [Apply]  [Apply & Load]                       │
│                                                  │
│ ▼ Manual Control                                │
│                                                  │
│   Gate: [T3 ▼]  Length: [100mm]  Speed: [50]   │
│                                                  │
│   [Feed →]  [← Retract]  [Stop]                │
│                                                  │
│ ▼ Dryer                                         │
│                                                  │
│   Status: Idle  │  Temp: 25°C  │  Time: --     │
│                                                  │
│   Target Temp: [50°C ▼]  Duration: [120 min]   │
│                                                  │
│   [Start Drying]  [Stop]                        │
│                                                  │
│ ▼ Health & Diagnostics                          │
│                                                  │
│   Overall: Excellent                            │
│                                                  │
│   Unit 1: ● Success: 99.8%  Avg: 45ms          │
│   Unit 2: ● Success: 99.9%  Avg: 42ms          │
│                                                  │
│   [Run Diagnostics]  [View Details]             │
│                                                  │
└─────────────────────────────────────────────────┘
```

### Expandable Sections Component

```vue
<template>
  <v-expansion-panels accordion flat>
    <!-- Devices Section -->
    <v-expansion-panel>
      <v-expansion-panel-header class="text-subtitle-2">
        Devices
      </v-expansion-panel-header>

      <v-expansion-panel-content>
        <div class="d-flex align-center mb-2">
          <span class="text-caption">Auto-Detect:</span>
          <v-chip x-small :color="autoDetect ? 'success' : 'grey'" class="ml-2">
            {{ autoDetect ? 'ON' : 'OFF' }}
          </v-chip>
          <v-spacer />
          <v-btn x-small @click="scanDevices">
            <v-icon left x-small>$refresh</v-icon>
            Scan
          </v-btn>
        </div>

        <v-list dense class="py-0">
          <v-list-item
            v-for="device in devices"
            :key="device.device_id"
            class="px-0"
          >
            <v-list-item-icon>
              <v-icon
                :color="device.connection_status === 'connected' ? 'success' : 'error'"
                small
              >
                {{ device.connection_status === 'connected' ? '$checkCircle' : '$alertCircle' }}
              </v-icon>
            </v-list-item-icon>

            <v-list-item-content>
              <v-list-item-title class="text-caption">
                {{ device.name }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                T{{ device.gates[0] }}-T{{ device.gates[device.gates.length - 1] }} │
                {{ device.port }} │
                {{ device.health.avg_response_time_ms }}ms
              </v-list-item-subtitle>
            </v-list-item-content>
          </v-list-item>
        </v-list>

        <div class="text-caption mt-2">
          Total: {{ totalGates }} gates across {{ deviceCount }} devices
        </div>
      </v-expansion-panel-content>
    </v-expansion-panel>

    <!-- Gate Configuration Section -->
    <v-expansion-panel>
      <v-expansion-panel-header class="text-subtitle-2">
        Gate Configuration
      </v-expansion-panel-header>

      <v-expansion-panel-content>
        <v-select
          v-model="selectedGate"
          :items="gateItems"
          label="Selected Gate"
          dense
          outlined
          hide-details
          class="mb-2"
        />

        <v-row dense>
          <v-col cols="6">
            <v-select
              v-model="gateMaterial"
              :items="materials"
              label="Material"
              dense
              outlined
              hide-details
            />
          </v-col>
          <v-col cols="6">
            <v-menu offset-y>
              <template #activator="{ on }">
                <v-btn
                  outlined
                  dense
                  block
                  v-on="on"
                >
                  <div
                    class="color-preview mr-2"
                    :style="{ backgroundColor: `#${gateColor}` }"
                  />
                  Color
                </v-btn>
              </template>
              <color-picker v-model="gateColor" />
            </v-menu>
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="6">
            <v-text-field
              v-model="gateTemp"
              label="Temperature"
              suffix="°C"
              type="number"
              dense
              outlined
              hide-details
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="spoolId"
              label="Spool ID"
              type="number"
              dense
              outlined
              hide-details
            />
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="6">
            <v-btn block small @click="applyConfig">
              Apply
            </v-btn>
          </v-col>
          <v-col cols="6">
            <v-btn block small color="primary" @click="applyAndLoad">
              Apply & Load
            </v-btn>
          </v-col>
        </v-row>
      </v-expansion-panel-content>
    </v-expansion-panel>

    <!-- Manual Control Section -->
    <v-expansion-panel>
      <v-expansion-panel-header class="text-subtitle-2">
        Manual Control
      </v-expansion-panel-header>

      <v-expansion-panel-content>
        <v-row dense>
          <v-col cols="4">
            <v-select
              v-model="controlGate"
              :items="gateItems"
              label="Gate"
              dense
              outlined
              hide-details
            />
          </v-col>
          <v-col cols="4">
            <v-text-field
              v-model="feedLength"
              label="Length"
              suffix="mm"
              type="number"
              dense
              outlined
              hide-details
            />
          </v-col>
          <v-col cols="4">
            <v-text-field
              v-model="feedSpeed"
              label="Speed"
              suffix="mm/s"
              type="number"
              dense
              outlined
              hide-details
            />
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="4">
            <v-btn block small @click="feed">
              <v-icon left x-small>$arrowDown</v-icon>
              Feed
            </v-btn>
          </v-col>
          <v-col cols="4">
            <v-btn block small @click="retract">
              <v-icon left x-small>$arrowUp</v-icon>
              Retract
            </v-btn>
          </v-col>
          <v-col cols="4">
            <v-btn block small color="error" @click="stop">
              <v-icon left x-small>$stop</v-icon>
              Stop
            </v-btn>
          </v-col>
        </v-row>
      </v-expansion-panel-content>
    </v-expansion-panel>

    <!-- Dryer Section -->
    <v-expansion-panel>
      <v-expansion-panel-header class="text-subtitle-2">
        Dryer
      </v-expansion-panel-header>

      <v-expansion-panel-content>
        <div class="dryer-status text-caption mb-2">
          <span>Status: {{ dryerStatus }}</span>
          <v-divider vertical class="mx-2" />
          <span>Temp: {{ currentTemp }}°C</span>
          <v-divider vertical class="mx-2" />
          <span>Time: {{ remainingTime }}</span>
        </div>

        <v-row dense>
          <v-col cols="6">
            <v-select
              v-model="targetTemp"
              :items="tempOptions"
              label="Target Temp"
              suffix="°C"
              dense
              outlined
              hide-details
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="dryerDuration"
              label="Duration"
              suffix="min"
              type="number"
              dense
              outlined
              hide-details
            />
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="6">
            <v-btn
              block
              small
              color="success"
              @click="startDrying"
              :disabled="dryerActive"
            >
              Start Drying
            </v-btn>
          </v-col>
          <v-col cols="6">
            <v-btn
              block
              small
              color="error"
              @click="stopDrying"
              :disabled="!dryerActive"
            >
              Stop
            </v-btn>
          </v-col>
        </v-row>
      </v-expansion-panel-content>
    </v-expansion-panel>

    <!-- Health & Diagnostics Section -->
    <v-expansion-panel>
      <v-expansion-panel-header class="text-subtitle-2">
        Health & Diagnostics
      </v-expansion-panel-header>

      <v-expansion-panel-content>
        <div class="health-overview mb-2">
          <span class="text-caption">Overall:</span>
          <v-chip x-small :color="overallHealthColor" class="ml-2">
            {{ overallHealth }}
          </v-chip>
        </div>

        <v-list dense class="py-0">
          <v-list-item
            v-for="device in devices"
            :key="`health-${device.device_id}`"
            class="px-0"
          >
            <v-list-item-icon>
              <v-icon :color="deviceHealthColor(device)" x-small>
                $circle
              </v-icon>
            </v-list-item-icon>

            <v-list-item-content>
              <v-list-item-title class="text-caption">
                {{ device.name }}
              </v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                Success: {{ (device.health.success_rate * 100).toFixed(1) }}% │
                Avg: {{ device.health.avg_response_time_ms }}ms
              </v-list-item-subtitle>
            </v-list-item-content>
          </v-list-item>
        </v-list>

        <v-row dense class="mt-2">
          <v-col cols="6">
            <v-btn block x-small @click="runDiagnostics">
              Run Diagnostics
            </v-btn>
          </v-col>
          <v-col cols="6">
            <v-btn block x-small @click="viewHealthDetails">
              View Details
            </v-btn>
          </v-col>
        </v-row>
      </v-expansion-panel-content>
    </v-expansion-panel>
  </v-expansion-panels>
</template>
```

---

## 3. Configuration Dialog

### Compact Color Picker

```
┌───────────────────────────────────────┐
│ Gate Configuration - T3          [×]  │
├───────────────────────────────────────┤
│                                        │
│ Material: [PETG ▼]                    │
│                                        │
│ Color:                                 │
│ ┌─┬─┬─┬─┬─┬─┬─┬─┐                     │
│ │█│█│█│█│█│█│█│█│                     │
│ └─┴─┴─┴─┴─┴▼┴─┴─┘                     │
│ ┌─┬─┬─┬─┬─┬─┬─┬─┐                     │
│ │█│█│█│█│█│█│█│█│                     │
│ └─┴─┴─┴─┴─┴─┴─┴─┘                     │
│                                        │
│ Custom: [#][0000FF____________]       │
│                                        │
│ Temperature: [230] °C                  │
│                                        │
│ Preview:                               │
│ ┌────────┐                            │
│ │   🔵   │                            │
│ │   T3   │                            │
│ │  PETG  │                            │
│ │  230°C │                            │
│ └────────┘                            │
│                                        │
│ [Cancel] [Apply] [Apply & Load]       │
└───────────────────────────────────────┘
```

---

## 4. Settings Page Integration

### ACE Manager Settings Panel

```
┌─────────────────────────────────────────────────┐
│ Settings → ACE Manager                           │
├─────────────────────────────────────────────────┤
│                                                  │
│ ▼ Device Detection                              │
│                                                  │
│   Auto-Detect: ⚫ Enabled                        │
│   ⓘ Automatically find and configure ACE devices│
│                                                  │
│   Device Map File: /config/ace_device_map.cfg   │
│   Last Updated: 2024-01-15 14:32:15             │
│                                                  │
│   [Scan for Devices] [Reset Device Map]         │
│                                                  │
│ ▼ Sensor Configuration                          │
│                                                  │
│   Extruder Sensor: [^EBBCan:PB9____________]    │
│   Toolhead Sensor: [EBBCan:PB8_____________]    │
│                                                  │
│ ▼ Speed Settings                                │
│                                                  │
│   Feed Speed:          [80] mm/s                │
│   Retract Speed:       [80] mm/s                │
│   Extruder Move Speed: [10] mm/s                │
│   Toolhead Homing:     [20] mm/s                │
│                                                  │
│ ▼ Advanced                                      │
│                                                  │
│   Toolchange Feed:     [800] mm                 │
│   Toolchange Retract:  [170] mm                 │
│   Sensor to Nozzle:    [40] mm                  │
│   Max Dryer Temp:      [70] °C                  │
│                                                  │
│   [Edit Config File] [Save] [Reset to Default]  │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 5. Status Bar Integration

### Compact Status Indicator

Add to Fluidd's top status bar:

```
┌──────────────────────────────────────────┐
│ [Fluidd Logo] Printer Name               │
│                                           │
│ Status │ ACE: T3 ● │ Temp │ Print        │
└──────────────────────────────────────────┘
```

**Clicking "ACE" opens quick menu:**
```
┌─────────────────────┐
│ ACE: T3 Active      │
├─────────────────────┤
│ Load T0 (PLA)       │
│ Load T1 (ABS)       │
│ Load T2 (Empty)     │
│ Load T3 (PETG) ✓    │
│ Load T4 (PLA)       │
│ Load T5 (Empty)     │
│ Load T6 (Empty)     │
│ Load T7 (TPU)       │
├─────────────────────┤
│ Unload Current      │
│ Configure...        │
└─────────────────────┘
```

---

## Design Tokens (Fluidd Theme)

### Colors (Dark Mode)
```css
--ace-bg-primary: #1a1d24
--ace-bg-secondary: #242831
--ace-border: rgba(255, 255, 255, 0.12)
--ace-text-primary: #ffffff
--ace-text-secondary: rgba(255, 255, 255, 0.7)
--ace-success: #4caf50
--ace-error: #f44336
--ace-warning: #ff9800
--ace-info: #2196f3
```

### Typography
```css
--ace-font-size-xs: 0.7rem
--ace-font-size-sm: 0.75rem
--ace-font-size-md: 0.875rem
--ace-font-size-lg: 1rem
```

### Spacing
```css
--ace-spacing-xs: 4px
--ace-spacing-sm: 8px
--ace-spacing-md: 12px
--ace-spacing-lg: 16px
```

---

## Performance Optimizations

### Lazy Loading
- Device cards load on demand
- Gate configuration dialog lazy loaded
- Health charts loaded when opened

### Virtual Scrolling
- Gate list virtualized for >16 gates
- Device list virtualized for >4 devices

### Debouncing
- Status updates debounced to 2s
- Configuration changes debounced to 500ms

---

## Mobile Responsive Design

### Breakpoints
- **Mobile**: < 600px - Single column, stacked cards
- **Tablet**: 600-960px - Two column where applicable
- **Desktop**: > 960px - Full layout

### Touch Optimizations
- Minimum touch target: 44×44px
- Larger spacing between interactive elements
- Swipe gestures for gate selection
- Pull-to-refresh for device scan

---

## Accessibility

### Keyboard Shortcuts
- `Alt+A`: Open ACE panel
- `Alt+G`: Focus gate selector
- `Alt+L`: Load selected gate
- `Alt+U`: Unload current gate
- `Esc`: Close dialogs

### Screen Reader Support
- ARIA labels on all controls
- Status announcements for gate changes
- Error messages announced
- Loading states announced

---

## Error States

### Connection Error
```
┌────────────────────────────────┐
│ ⚠ Connection Lost              │
├────────────────────────────────┤
│ ACE Unit 1 disconnected        │
│                                 │
│ Attempting to reconnect...     │
│ ████░░░░ 50%                   │
│                                 │
│ [Retry] [Cancel]               │
└────────────────────────────────┘
```

### No Devices Found
```
┌────────────────────────────────┐
│ No ACE Devices Found           │
├────────────────────────────────┤
│ • Check USB connections        │
│ • Verify auto-detect enabled   │
│ • Check device power           │
│                                 │
│ [Scan Again] [Manual Setup]    │
└────────────────────────────────┘
```

---

This specification provides a complete, production-ready UI design for Fluidd that prioritizes minimalism, performance, and information density while maintaining full feature parity with Mainsail.

