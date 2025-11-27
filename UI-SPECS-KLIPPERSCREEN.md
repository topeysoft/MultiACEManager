# KlipperScreen UI Specification for ACE Manager

## Overview
Enhanced UI/UX design for ACE multi-device management in KlipperScreen, optimized for touchscreen displays with focus on visual clarity, large touch targets, and intuitive workflows.

## Design Philosophy
- **Touch-first**: All controls optimized for touchscreen use (minimum 48×48px targets)
- **Visual hierarchy**: Most important information prominently displayed
- **Minimal text entry**: Use pickers and selectors instead of keyboards
- **Clear feedback**: Visual and tactile feedback for all interactions
- **Existing integration**: Enhance current [ace.py](KlipperScreen/panels/ace.py) implementation

---

## 1. Main ACE Panel (Enhanced)

### Layout Overview

Based on existing implementation in `KlipperScreen/panels/ace.py`, with enhancements:

```
┌─────────────────────────────────────────────────────────────┐
│ ACE Pro                                             [Menu]   │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────── Gate Slots ──────────────────────────────┐ │
│ │ ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐      │ │
│ │ │  1  │  2  │  3  │  4  │  5  │  6  │  7  │  8  │      │ │
│ │ │ PLA │ ABS │ --- │PETG │ PLA │ --- │ --- │ TPU │      │ │
│ │ │ 🔴 │ 🟡 │ ⚪ │ 🔵 │ 🔴 │ ⚪ │ ⚪ │ 🟣 │      │ │
│ │ │     │     │     │ ✓   │     │     │     │     │      │ │
│ │ └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘      │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌───────── Filament Path Visualization ──────────────────┐  │
│ │ Gate → ████████████████████░░░░░░ → Toolhead            │ │
│ │  3        Inlet    Outlet  Sensor                       │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌────────── Status Info ─────────────────────────────────┐  │
│ │ 🟢 Ready │ 25°C │ ⏱ --:--:-- │ Feed: OFF │ Endless: OFF │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌──────────── Controls ────────────────────────────────────┐ │
│ │ [📦 Pre-Load] [⏏ Eject] [⏹ Stop] [🔥 Dryer] [⚙ More]  │ │
│ └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Gate Slot Widget (Enhanced)

**Current**: Basic spool with number
**Enhanced**: Add device grouping for multi-ACE setups

```python
def create_slot_widget(self, index):
    """Enhanced slot widget with device awareness"""
    # Determine which ACE device this gate belongs to
    device_num = index // 4  # 0-3 = Device 1, 4-7 = Device 2, etc.
    local_gate = index % 4

    # Use EventBox to make entire slot clickable
    event_box = Gtk.EventBox()
    event_box.connect("button-press-event", self.on_slot_clicked, index)

    slot_frame = Gtk.Frame()
    slot_frame.get_style_context().add_class("ace-slot-frame")

    # Add device indicator for multi-ACE setups
    if self.num_devices > 1:
        device_indicator = Gtk.Label()
        device_indicator.set_markup(f"<small>Unit {device_num + 1}</small>")
        device_indicator.get_style_context().add_class("ace-device-badge")

    # Stack for normal/action views
    stack = Gtk.Stack()
    stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
    stack.set_transition_duration(150)

    # Normal view with enhanced visual feedback
    normal_box = self._create_slot_normal_view(index, device_num, local_gate)

    # Action view with Select/Edit/More options
    action_box = self._create_slot_action_view(index)

    stack.add_named(normal_box, "normal")
    stack.add_named(action_box, "action")
    stack.set_visible_child_name("normal")

    self.slot_widgets[f'stack_{index}'] = stack

    slot_frame.add(stack)
    event_box.add(slot_frame)

    return event_box
```

### Multi-Device Indicator

For systems with multiple ACE units, add device grouping:

```
┌─────────────────────────────────────────────────────┐
│ ┌── ACE Unit 1 ──────────────────────────────────┐ │
│ │ ┌─────┬─────┬─────┬─────┐                      │ │
│ │ │  1  │  2  │  3  │  4  │  ✓ Connected  45ms   │ │
│ │ │ PLA │ ABS │ --- │PETG │                      │ │
│ │ └─────┴─────┴─────┴─────┘                      │ │
│ └─────────────────────────────────────────────────┘ │
│                                                     │
│ ┌── ACE Unit 2 ──────────────────────────────────┐ │
│ │ ┌─────┬─────┬─────┬─────┐                      │ │
│ │ │  5  │  6  │  7  │  8  │  ✓ Connected  42ms   │ │
│ │ │ PLA │ --- │ --- │ TPU │                      │ │
│ │ └─────┴─────┴─────┴─────┘                      │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## 2. Gate Configuration Panel (Enhanced)

### Current Implementation
Based on `create_gate_config_panel()` in ace.py

### Enhanced Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back          Configure Gate 3                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ┌──────────── Preview ────────────────┐                     │
│ │                                      │                     │
│ │          ┌──────────┐                │                     │
│ │          │          │                │                     │
│ │          │   🔵     │                │                     │
│ │          │    3     │   PETG         │                     │
│ │          │          │   230°C        │                     │
│ │          └──────────┘                │                     │
│ │                                      │                     │
│ └──────────────────────────────────────┘                     │
│                                                              │
│ Material:                                                    │
│ ┌────┬────┬────┬────┬────┬────┬────┬────┐                  │
│ │PLA │ABS │ASA │PETG│TPU │ PA │ PC │PVA │                  │
│ └────┴────┴────┴─✓─┴────┴────┴────┴────┘                  │
│                                                              │
│ Color:                                                       │
│ ┌───┬───┬───┬───┬───┬───┬───┬───┐                          │
│ │🔴│🟠│🟡│🟢│🔵│🟣│⚫│⚪│                          │
│ └───┴───┴───┴───┴─✓─┴───┴───┴───┘                          │
│ ┌───┬───┬───┬───┬───┬───┬───┬───┐                          │
│ │🟤│💖│🌈│✨│🎨│🎯│🔶│◻️│                          │
│ └───┴───┴───┴───┴───┴───┴───┴───┘                          │
│                                                              │
│ Temperature: ┌────────────────────────┐                     │
│              │ 180° ─────●───── 280°  │                     │
│              └────────────────────────┘                     │
│              230°C                                           │
│                                                              │
│ ┌─ Advanced Settings ──────────────────────────────────────┐│
│ │ Custom Name:  [Optional Text Entry          ]           ││
│ │ Spool Weight: [1000g ▼]                                 ││
│ │ Endless Group: [None ▼]                                 ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ [Cancel]    [Apply]    [Apply & Load]                  │  │
│ └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Enhanced Color Picker with Emoji Support

```python
def create_color_picker_enhanced(self):
    """Enhanced color picker with emoji indicators"""
    color_grid = Gtk.Grid(
        column_homogeneous=True,
        row_homogeneous=True,
        row_spacing=8,
        column_spacing=8
    )

    # Row 1: Standard colors
    standard_colors = [
        ('FF0000', '🔴'),  # Red
        ('FF8000', '🟠'),  # Orange
        ('FFFF00', '🟡'),  # Yellow
        ('00FF00', '🟢'),  # Green
        ('0000FF', '🔵'),  # Blue
        ('8000FF', '🟣'),  # Purple
        ('000000', '⚫'),  # Black
        ('FFFFFF', '⚪'),  # White
    ]

    # Row 2: Extended colors
    extended_colors = [
        ('8B4513', '🟤'),  # Brown
        ('FF69B4', '💖'),  # Pink
        ('RAINBOW', '🌈'),  # Rainbow gradient (special)
        ('FFD700', '✨'),  # Gold sparkle
        ('FF1493', '🎨'),  # Deep pink (art)
        ('32CD32', '🎯'),  # Lime green (target)
        ('FFA500', '🔶'),  # Orange diamond
        ('D3D3D3', '◻️'),  # Light gray
    ]

    row = 0
    for colors in [standard_colors, extended_colors]:
        for col, (color_hex, emoji) in enumerate(colors):
            btn = self._create_color_button(color_hex, emoji)
            color_grid.attach(btn, col, row, 1, 1)
        row += 1

    return color_grid

def _create_color_button(self, color_hex, emoji):
    """Create a color button with emoji overlay"""
    btn = Gtk.Button()
    btn.set_size_request(80, 80)

    # Create overlay with color background and emoji
    overlay = Gtk.Overlay()

    # Color background
    drawing_area = Gtk.DrawingArea()
    drawing_area.set_size_request(80, 80)
    drawing_area.connect("draw", self.draw_color_background, color_hex)

    # Emoji label
    emoji_label = Gtk.Label(label=emoji)
    emoji_label.set_halign(Gtk.Align.CENTER)
    emoji_label.set_valign(Gtk.Align.CENTER)
    emoji_label.get_style_context().add_class("ace-color-emoji")

    overlay.add(drawing_area)
    overlay.add_overlay(emoji_label)

    btn.add(overlay)
    btn.connect("clicked", self.select_config_color_enhanced, color_hex)

    btn.get_style_context().add_class("ace-color-btn")

    return btn
```

---

## 3. Device Management Panel (New)

### New Panel for Multi-Device Setups

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back          ACE Devices                                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Auto-Detect: ●ON    Total Gates: 8    [🔍 Scan]            │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ ACE Unit 1                                             │  │
│ │ ┌──────────────────────────────────────────────────┐  │  │
│ │ │ ✓ Connected │ ACE PRO v2.1.0 │ /dev/ttyACM0     │  │  │
│ │ │ Gates: 0-3  │ Response: 45ms │ Health: Excellent │  │  │
│ │ └──────────────────────────────────────────────────┘  │  │
│ │                                                         │  │
│ │ ┌─ Gates ──────────────────────┐                       │  │
│ │ │ 1:PLA  2:ABS  3:---  4:PETG  │                       │  │
│ │ │  ●      ●      ○      ●      │                       │  │
│ │ └──────────────────────────────┘                       │  │
│ │                                                         │  │
│ │ [📊 Health] [⚙ Configure] [🔄 Reconnect]              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ ┌────────────────────────────────────────────────────────┐  │
│ │ ACE Unit 2                                             │  │
│ │ ┌──────────────────────────────────────────────────┐  │  │
│ │ │ ✓ Connected │ ACE PRO v2.1.0 │ /dev/ttyACM1     │  │  │
│ │ │ Gates: 4-7  │ Response: 42ms │ Health: Good      │  │  │
│ │ └──────────────────────────────────────────────────┘  │  │
│ │                                                         │  │
│ │ ┌─ Gates ──────────────────────┐                       │  │
│ │ │ 5:PLA  6:---  7:---  8:TPU   │                       │  │
│ │ │  ●      ○      ○      ●      │                       │  │
│ │ └──────────────────────────────┘                       │  │
│ │                                                         │  │
│ │ [📊 Health] [⚙ Configure] [🔄 Reconnect]              │  │
│ └────────────────────────────────────────────────────────┘  │
│                                                              │
│ [+ Add Device Manually]                                     │
└─────────────────────────────────────────────────────────────┘
```

### Implementation

```python
def create_device_management_panel(self):
    """Create device management panel for multi-ACE setups"""
    grid = Gtk.Grid(
        column_homogeneous=False,
        row_homogeneous=False,
        row_spacing=10,
        column_spacing=10
    )

    # Header
    header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

    auto_detect_label = Gtk.Label(label="Auto-Detect:")
    auto_detect_indicator = Gtk.Label()
    auto_detect_indicator.set_markup("<b>●ON</b>")
    auto_detect_indicator.get_style_context().add_class("ace-status-on")

    total_gates_label = Gtk.Label()
    total_gates_label.set_markup(f"<b>Total Gates: {self.total_gates}</b>")

    scan_btn = self._gtk.Button("refresh", "Scan")
    scan_btn.connect("clicked", self.scan_devices)

    header_box.pack_start(auto_detect_label, False, False, 0)
    header_box.pack_start(auto_detect_indicator, False, False, 0)
    header_box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 10)
    header_box.pack_start(total_gates_label, False, False, 0)
    header_box.pack_end(scan_btn, False, False, 0)

    grid.attach(header_box, 0, 0, 1, 1)

    # Device cards
    row = 1
    for device_info in self.ace_devices:
        device_card = self._create_device_card(device_info)
        grid.attach(device_card, 0, row, 1, 1)
        row += 1

    # Add device button
    add_device_btn = self._gtk.Button("plus", "Add Device Manually")
    add_device_btn.connect("clicked", self.add_device_manually)
    grid.attach(add_device_btn, 0, row, 1, 1)

    return grid

def _create_device_card(self, device_info):
    """Create an expandable device card"""
    card_frame = Gtk.Frame()
    card_frame.get_style_context().add_class("ace-device-card")

    card_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    card_box.set_margin_start(10)
    card_box.set_margin_end(10)
    card_box.set_margin_top(10)
    card_box.set_margin_bottom(10)

    # Device name
    name_label = Gtk.Label()
    name_label.set_markup(f"<big><b>{device_info['name']}</b></big>")
    name_label.set_halign(Gtk.Align.START)

    # Device info grid
    info_grid = Gtk.Grid(column_homogeneous=True, row_homogeneous=True, column_spacing=10)

    status_label = self._create_info_label("✓ Connected", "success")
    model_label = self._create_info_label(f"{device_info['model']} v{device_info['firmware']}")
    port_label = self._create_info_label(device_info['port'])

    gates_label = self._create_info_label(f"Gates: {device_info['gates'][0]}-{device_info['gates'][-1]}")
    response_label = self._create_info_label(f"Response: {device_info['health']['avg_response_time_ms']}ms")
    health_label = self._create_info_label(f"Health: {device_info['health']['status'].title()}", "info")

    info_grid.attach(status_label, 0, 0, 1, 1)
    info_grid.attach(model_label, 1, 0, 1, 1)
    info_grid.attach(port_label, 2, 0, 1, 1)
    info_grid.attach(gates_label, 0, 1, 1, 1)
    info_grid.attach(response_label, 1, 1, 1, 1)
    info_grid.attach(health_label, 2, 1, 1, 1)

    # Gates preview
    gates_frame = Gtk.Frame(label="Gates")
    gates_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

    for gate_id in device_info['gates']:
        gate_preview = self._create_gate_preview_mini(gate_id)
        gates_box.pack_start(gate_preview, True, True, 0)

    gates_frame.add(gates_box)

    # Action buttons
    actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

    health_btn = self._gtk.Button("chart-line", "Health")
    health_btn.connect("clicked", self.show_device_health, device_info['device_id'])

    configure_btn = self._gtk.Button("settings", "Configure")
    configure_btn.connect("clicked", self.configure_device, device_info['device_id'])

    reconnect_btn = self._gtk.Button("refresh", "Reconnect")
    reconnect_btn.connect("clicked", self.reconnect_device, device_info['device_id'])

    actions_box.pack_start(health_btn, True, True, 0)
    actions_box.pack_start(configure_btn, True, True, 0)
    actions_box.pack_start(reconnect_btn, True, True, 0)

    # Assemble card
    card_box.pack_start(name_label, False, False, 0)
    card_box.pack_start(info_grid, False, False, 0)
    card_box.pack_start(gates_frame, False, False, 0)
    card_box.pack_start(actions_box, False, False, 0)

    card_frame.add(card_box)

    return card_frame
```

---

## 4. Health Monitoring Panel (New)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back          Device Health                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ACE Unit 1                                                   │
│                                                              │
│ ┌─ Overall Health ──────────────────────────────────────┐   │
│ │ Status: ● Excellent                                    │   │
│ │ Success Rate: 99.8%  │  Avg Response: 45ms            │   │
│ │ Total Requests: 15,234  │  Errors: 32                 │   │
│ │ Uptime: 24h 15m  │  Connection Cycles: 1              │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌─ Response Time Chart ─────────────────────────────────┐   │
│ │                                                         │   │
│ │  100ms │                     ●                         │   │
│ │   80ms │        ●     ●                                │   │
│ │   60ms │  ●                       ●                    │   │
│ │   40ms │                 ●              ●        ●    │   │
│ │   20ms │                                               │   │
│ │    0ms └─────────────────────────────────────────────  │   │
│ │         Last 10 requests                              │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ ┌─ Recent Errors ───────────────────────────────────────┐   │
│ │ • Request timeout (2 hours ago)                        │   │
│ │ • CRC mismatch (5 hours ago)                          │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ [Run Diagnostics] [View Detailed Stats] [Export Log]       │
└─────────────────────────────────────────────────────────────┘
```

### Simple Text-Based Chart

```python
def draw_response_time_chart_simple(self, widget, cr, response_times):
    """Draw simple ASCII-style response time chart"""
    width = widget.get_allocated_width()
    height = widget.get_allocated_height()

    # Background
    cr.set_source_rgb(0.1, 0.1, 0.1)
    cr.rectangle(0, 0, width, height)
    cr.fill()

    if not response_times or len(response_times) == 0:
        return

    # Calculate scales
    max_time = max(response_times)
    min_time = min(response_times)
    time_range = max_time - min_time if max_time != min_time else 1

    # Grid lines
    cr.set_source_rgba(0.3, 0.3, 0.3, 0.5)
    cr.set_line_width(1)
    for i in range(5):
        y = height * (i / 4)
        cr.move_to(0, y)
        cr.line_to(width, y)
        cr.stroke()

    # Plot points
    cr.set_source_rgb(0.3, 0.8, 0.3)  # Green
    point_spacing = width / (len(response_times) - 1) if len(response_times) > 1 else width

    for i, time_val in enumerate(response_times):
        x = i * point_spacing
        # Invert Y axis (higher values at top)
        normalized = (time_val - min_time) / time_range
        y = height - (normalized * height)

        # Draw circle
        cr.arc(x, y, 4, 0, 2 * 3.14159)
        cr.fill()

    # Connect with line
    cr.set_source_rgba(0.3, 0.8, 0.3, 0.5)
    cr.set_line_width(2)
    for i in range(len(response_times) - 1):
        x1 = i * point_spacing
        normalized1 = (response_times[i] - min_time) / time_range
        y1 = height - (normalized1 * height)

        x2 = (i + 1) * point_spacing
        normalized2 = (response_times[i + 1] - min_time) / time_range
        y2 = height - (normalized2 * height)

        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()

    # Labels
    cr.set_source_rgb(0.7, 0.7, 0.7)
    cr.select_font_face("Sans", 0, 0)
    cr.set_font_size(10)

    # Y-axis labels
    for i in range(5):
        value = max_time - (i * (time_range / 4))
        text = f"{value:.0f}ms"
        cr.move_to(5, height * (i / 4) + 10)
        cr.show_text(text)

    # X-axis label
    cr.move_to(width - 100, height - 5)
    cr.show_text(f"Last {len(response_times)} requests")
```

---

## 5. Advanced Settings Panel (Enhanced)

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ ← Back          Advanced Settings                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ ▼ Device Configuration                                      │
│ │ Auto-Detect Devices: ⚫ ON                                │
│ │ Device Map File: /config/ace_device_map.cfg              │
│ │ [Scan Devices] [Reset Device Map]                        │
│                                                              │
│ ▼ Sensor Pins                                               │
│ │ Extruder Sensor: [^EBBCan:PB9                    ]       │
│ │ Toolhead Sensor: [EBBCan:PB8                     ]       │
│ │ [Test Sensors]                                            │
│                                                              │
│ ▼ Speed Settings (mm/s)                                     │
│ │ Feed Speed:          ┌────●────┐ 80                      │
│ │ Retract Speed:       ┌────●────┐ 80                      │
│ │ Extruder Move:       ┌──●──────┐ 10                      │
│ │ Toolhead Homing:     ┌───●─────┐ 20                      │
│                                                              │
│ ▼ Advanced Parameters (mm)                                  │
│ │ Toolchange Feed:     ┌──────────●──┐ 800                │
│ │ Toolchange Retract:  ┌────●────────┐ 170                │
│ │ Sensor to Nozzle:    ┌──●──────────┐ 40                 │
│                                                              │
│ ▼ Firmware & Diagnostics                                    │
│ │ Check Firmware Versions: [Check Now]                     │
│ │ Run Full Diagnostics:    [Run Diagnostics]               │
│ │ Export Configuration:    [Export]                         │
│ │ View Logs:              [View Logs]                      │
│                                                              │
│ [Reset to Defaults] [Save Configuration]                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Touch Interaction Patterns

### Gestures

**Swipe Gestures:**
- **Swipe left/right on gate slots**: Navigate between gates
- **Swipe up on main panel**: Open quick actions
- **Swipe down**: Refresh status

**Long Press:**
- **Long press gate**: Open configuration
- **Long press device card**: Show device options menu

**Tap Patterns:**
- **Single tap gate**: Select/deselect
- **Double tap gate**: Load immediately
- **Tap and hold**: Show preview/tooltip

### Implementation

```python
class TouchGestureHandler:
    """Handle touch gestures for ACE panel"""

    def __init__(self, panel):
        self.panel = panel
        self.touch_start = None
        self.long_press_timer = None
        self.LONG_PRESS_DURATION = 500  # ms
        self.SWIPE_THRESHOLD = 100  # pixels

    def on_touch_begin(self, widget, event):
        """Handle touch begin event"""
        self.touch_start = (event.x, event.y, event.time)

        # Start long press timer
        self.long_press_timer = GLib.timeout_add(
            self.LONG_PRESS_DURATION,
            self.on_long_press,
            widget,
            event
        )

        return True

    def on_touch_end(self, widget, event):
        """Handle touch end event"""
        # Cancel long press if active
        if self.long_press_timer:
            GLib.source_remove(self.long_press_timer)
            self.long_press_timer = None

        if not self.touch_start:
            return True

        # Calculate swipe distance
        dx = event.x - self.touch_start[0]
        dy = event.y - self.touch_start[1]
        distance = (dx**2 + dy**2) ** 0.5

        # Detect swipe
        if distance > self.SWIPE_THRESHOLD:
            if abs(dx) > abs(dy):
                # Horizontal swipe
                if dx > 0:
                    self.on_swipe_right(widget)
                else:
                    self.on_swipe_left(widget)
            else:
                # Vertical swipe
                if dy > 0:
                    self.on_swipe_down(widget)
                else:
                    self.on_swipe_up(widget)
        else:
            # Regular tap
            self.on_tap(widget, event)

        self.touch_start = None
        return True

    def on_long_press(self, widget, event):
        """Handle long press"""
        # Determine which gate was long-pressed
        gate_index = self.panel.get_gate_at_position(event.x, event.y)

        if gate_index is not None:
            self.panel.open_gate_config(None, gate_index)

        self.long_press_timer = None
        return False  # Don't repeat

    def on_swipe_left(self, widget):
        """Swipe left - next gate"""
        self.panel.select_next_gate()

    def on_swipe_right(self, widget):
        """Swipe right - previous gate"""
        self.panel.select_previous_gate()

    def on_swipe_up(self, widget):
        """Swipe up - quick actions"""
        self.panel.show_quick_actions()

    def on_swipe_down(self, widget):
        """Swipe down - refresh"""
        self.panel.refresh_status()

    def on_tap(self, widget, event):
        """Handle regular tap"""
        # Default tap handling
        widget.emit("button-press-event", event)
```

---

## 7. Accessibility Features

### Large Text Mode

Add support for visually impaired users:

```python
def apply_accessibility_mode(self, large_text=True, high_contrast=True):
    """Apply accessibility enhancements"""
    css_provider = Gtk.CssProvider()

    if large_text:
        css = """
        .ace-slot-frame {
            font-size: 24px;
        }
        .ace-material-label {
            font-size: 20px;
        }
        .gate-number {
            font-size: 28px;
        }
        """
        css_provider.load_from_data(css.encode())

    if high_contrast:
        css += """
        .ace-slot-ready {
            border: 4px solid #00FF00;
        }
        .ace-slot-empty {
            border: 4px solid #FF0000;
        }
        .ace-slot-selected {
            border: 6px solid #FFFF00;
            background: rgba(255, 255, 0, 0.2);
        }
        """
        css_provider.load_from_data(css.encode())

    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        css_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
```

### Voice Feedback (Optional)

For headless operation:

```python
def announce_status(self, message):
    """Announce status via TTS (if available)"""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(message)
        engine.runAndWait()
    except ImportError:
        # TTS not available, use visual feedback only
        pass
```

---

## 8. CSS Styling

### Enhanced Theme

```css
/* ACE Panel Styles */
.ace-slot-frame {
    border-radius: 8px;
    padding: 8px;
    margin: 4px;
    transition: all 0.2s;
}

.ace-slot-ready {
    border: 2px solid #4CAF50;
    background: rgba(76, 175, 80, 0.1);
}

.ace-slot-empty {
    border: 2px solid #9E9E9E;
    background: rgba(158, 158, 158, 0.1);
    opacity: 0.6;
}

.ace-slot-selected {
    border: 3px solid #2196F3;
    background: rgba(33, 150, 243, 0.2);
    transform: scale(1.05);
}

.ace-device-card {
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 8px;
    padding: 12px;
    background: rgba(0, 0, 0, 0.3);
}

.ace-device-badge {
    background: rgba(33, 150, 243, 0.3);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
}

.ace-status-on {
    color: #4CAF50;
}

.ace-status-off {
    color: #9E9E9E;
}

.ace-color-btn {
    border: 2px solid transparent;
    border-radius: 8px;
    transition: all 0.2s;
}

.ace-color-btn:hover {
    border-color: #FFFFFF;
    transform: scale(1.1);
}

.ace-color-emoji {
    font-size: 32px;
    text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
}
```

---

This comprehensive KlipperScreen specification provides a complete, touch-optimized UI for ACE management with enhanced multi-device support, accessibility features, and intuitive gesture controls.

