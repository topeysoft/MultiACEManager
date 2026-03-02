<div align="center">

<!-- LOGO PLACEHOLDER -->
<img style="margin-top: 15px; margin-bottom: -15px; margin-left: 25px" src="./.github/img/logo.svg" alt="KlipperACE" width="120" height="120" />
<h1 style="margin-top: 0">KlipperACE</h1>

[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE.md)
![Status](https://img.shields.io/badge/Status-WIP-orange)
![Klipper](https://img.shields.io/badge/Klipper-Module-blue)
![Anycubic ACE](https://img.shields.io/badge/Anycubic-ACE%20Pro-8A2BE2)

<p>Driver for Anycubic Color Engine Pro (ACE) for Klipper</p>
<p>Control filament feed, tool change (up to 16 channels with multi-ACE), ACE dryer, and workflows right from Klipper/G-code.</p>

</div>

---

## 🧭 Table of Contents

- [Features](#-features)
- [Requirements](#-requirements)
- [Installation](#-installation)
- [Update](#-update)
- [Uninstall](#-uninstall)
- [Quick Start](#-quick-start)
- [Device Chaining](#-device-chaining)
- [Configuration (acecfg)](#-configuration-acecfg)
- [G-code Commands](#-g-code-commands)
- [Sensors and Logic](#-sensors-and-logic)
- [Typical Workflow](#-typical-workflow)
- [Pinout and Wiring](#-pinout-and-wiring)
- [Debug and Logs](#-debug-and-logs)
- [Roadmap](#-roadmap)
- [License](#-license)
- [Authors and Contributors](#-authors-and-contributors)

## ✨ Features

- **Multi-ACE Support**: Use 2, 3, 4, or more ACE Pro devices for 8, 12, 16+ gates 🔀
- **ACE Manager**: Unified interface across all ACE units with automatic routing
- Up to 4 gates per ACE device
- Feed Assist on ACE side
- ACE Pro dryer control: start by temperature/time and stop ♨️
- Gate mapping: color, material, recommended temperature 🎯
- Endless Spool mode (auto-switch when filament ends) ♾️
- Integration with filament sensors and Klipper macros 🧩

## 📦 Requirements

- Klipper + Moonraker
- Terminal access to the device running Klipper

## ⚙️ Installation

The script will automatically install the latest driver version.

Remove/comment any sections about your current filament runout sensor in your printer.cfg since you are going to use extruder filament sensor for runout detection.

```bash
cd ~
git clone https://github.com/topeysoft/MultiACEManager.git KlipperACE
cd KlipperACE
./install.sh
```

After installation:

- Add [include ace.cfg] to your printer.cfg.
- Moonraker will show an Update Manager entry "KlipperACE" for updates from the web UI.

Important: if you already have your own [save_variables], move variables from ace_vars.cfg into your variables file and comment out the [save_variables] block in ace.cfg.

## 🔄 Update

- Via Web UI: Moonraker Update Manager → KlipperACE

## 🗑️ Uninstall

1. Remove [include ace.cfg] from your Klipper configuration and the update section from moonraker.conf.
2. Run:

```bash
cd ~/KlipperACE
./install.sh -u
```

## 🚀 Quick Start

1. Connect ACE via USB to the Klipper host.
2. Add/verify config: `ace.cfg`. Minimum:
   - serial: path to ACE (e.g., `/dev/serial/by-id/usb-ANYCUBIC_ACE_1-if00`)
   - `extruder_sensor_pin:` filament sensor pin at the extruder
   - `toolhead_sensor_pin:` sensor pin before the cutter (if present)
   - `toolchange_retract_length:` you must specify the distance from the splitter to your printer head
   - `poop_macros` you must provide a nozzle purge macro
   - `cut_macros` you must provide a filament tip cut macro
3. Restart Klipper — the console will show a message about successful ACE connection (model and firmware).
4. Test tool change: `T0` / `T1` / `T2` / `T3` (or `ACE_CHANGE_TOOL TOOL=0..3`).

## 🔗 Multi-ACE Setup

**IMPORTANT**: ACE Pro "daisy-chaining" is for **filament routing only**. Each ACE Pro is a separate USB device that must be configured individually.

### How Multi-ACE Actually Works

- **Physical**: ACE units are daisy-chained for filament path (ACE1 → ACE2 → ACE3...)
- **USB**: Each ACE creates its own USB device (built-in USB hub)
- **Communication**: Each ACE reports its own 4 slots independently
- **KlipperACE Solution**: Use `[ace]` with `serial_ports` or `auto_detect` to aggregate multiple ACEs into a unified system
- **Moonraker integration**: `[ace_manager]` provides REST API endpoints for web UIs (Mainsail/Fluidd) — goes in `moonraker.conf`, not `printer.cfg`

### Quick Setup (5 Minutes - 2 ACEs = 8 Gates)

1. **Auto-detect and generate config**:

   ```bash
   cd ~/printer_data/config
   python3 ~/KlipperACE/probe_ace_ports.py --generate-config
   ```

2. **Copy the output** to your `ace.cfg` or `printer.cfg`

3. **Update sensor pins** (the two lines marked "Update this!")

4. **Restart Klipper** and test with `ACE_GET_STATUS`

**That's it!** Your 8-gate system is ready.

### Configuration Methods

#### Method 1: Simple Serial Ports (Recommended)

```ini
[ace]
serial_ports: /dev/ttyACM0, /dev/ttyACM1
extruder_sensor_pin: ^EBBCan: PB9
# All shared settings in one place
```

#### Method 2: Auto-Detection

```ini
[ace]
auto_detect: true
extruder_sensor_pin: ^EBBCan: PB9
# System finds ACE devices automatically
```

### Supported Configurations

- **2 ACEs**: 8 gates (T0-T7)
- **3 ACEs**: 12 gates (T0-T11)
- **4 ACEs**: 16 gates (T0-T15)
- **More**: No limit! Add as many as you want

### Documentation

- **[QUICK_REFERENCE.md](./QUICK_REFERENCE.md)** - Cheat sheet with common commands and config
- **[CONFIGURATION_REFERENCE.md](./CONFIGURATION_REFERENCE.md)** - Complete configuration parameter reference
- **[USB_PORT_MAPPING_GUIDE.md](./USB_PORT_MAPPING_GUIDE.md)** - USB port-based device identification
- **[DEVICE_ALIASING_GUIDE.md](./DEVICE_ALIASING_GUIDE.md)** - Friendly device naming
- **[FEED_RECOVERY_GUIDE.md](./FEED_RECOVERY_GUIDE.md)** - Feed timeout recovery workflow

### Example Configs

- **ace.cfg** - Recommended for most users (works for single or multi-ACE)
- **ace_manager_auto_detect.cfg** - Auto-detection method

### Single ACE vs Multi-ACE

Both single and multi-ACE setups use the same `[ace]` configuration section. Simply list one or more serial ports:

**Single ACE (4 gates)**:

```ini
[ace]
serial_ports: /dev/ttyACM0
```

**Multiple ACEs (8+ gates)**:

```ini
[ace]
serial_ports: /dev/ttyACM0, /dev/ttyACM1
```

Alternatively, use `auto_detect: true` to find all connected ACE devices automatically.

## 🛠️ Configuration (ace.cfg)

Main parameters (see [CONFIGURATION_REFERENCE.md](./CONFIGURATION_REFERENCE.md) for full list):

**Connection:**

- `serial_ports:` comma-separated ACE paths, or `auto_detect: true`
- `baud:` serial speed (default `115200`)

**Sensors:**

- `extruder_sensor_pin:` extruder sensor pin — **required** (e.g., `^EBBCan: PB9`)
- `toolhead_sensor_pin:` sensor pin before the cutter (optional, enables dual-sensor mode)

**Distances** (must tune for your setup):

- `toolchange_retract_length:` splitter to extruder distance in mm
- `toolchange_feed_length:` total feed length in mm
- `toolhead_sensor_to_nozzle:` sensor to nozzle in mm (dual-sensor mode)
- `extruder_sensor_to_nozzle:` sensor to nozzle in mm (single-sensor mode)

**Speeds:**

- `feed_speed:` `10–80` mm/s (default `50`) | `retract_speed:` `10–80` mm/s (default `50`)

**Temperature:**

- `enable_temp_preheat:` auto-preheat before tool change (default `true`)
- `temp_preheat_threshold:` delta to trigger preheat (default `20°C`)
- `max_dryer_temperature:` dryer temperature limit (default `55°C`)

**Macros:**

- `poop_macros:` purge macro after load | `cut_macros:` tip cut macro on unload
- `error_macros:` optional error handler macro (see [FEED_RECOVERY_GUIDE.md](./FEED_RECOVERY_GUIDE.md))

**Behavior:**

- `auto_register_t_macros:` auto-generate T0..TN macros (default `false`)
- `adaptive_polling:` smart poll rate based on activity (default `true`)

Templates at the end of `ace.cfg`:

- `_POOP` — purge | `_CUT_TIP` — tip cut
- `_ACE_PRE_TOOLCHANGE` / `_ACE_POST_TOOLCHANGE` — pre/post toolchange macros
- `T0..T15` — shortcuts to `ACE_CHANGE_TOOL`

Variables are saved in `ace_vars.cfg` via `[save_variables]`.

## ⌨️ G-code Commands

ACE adds commands available from Klipper console/macros. For a quick cheat sheet, see [QUICK_REFERENCE.md](./QUICK_REFERENCE.md).

### Tool Change & Filament Movement

- `ACE_CHANGE_TOOL TOOL=<-1..N> [SKIP_PREHEAT=<0|1>]` — change tool (TOOL=-1 unloads)
- `ACE_FEED INDEX=<0..N> LENGTH=<mm> [SPEED=<mm/s>]` — feed filament from ACE side
- `ACE_RETRACT INDEX=<0..N> LENGTH=<mm> [SPEED=<mm/s>]` — retract filament into ACE
- `ACE_SET_GATE GATE=<n>` — set selected gate without loading (for manual filament sync)
- `ACE_CLEAR_SELECTION` — clear selected gate without unloading
- `ACE_ENABLE_FEED_ASSIST INDEX=<0..N>` — enable feed assist for a channel
- `ACE_DISABLE_FEED_ASSIST [INDEX=<0..N>]` — disable feed assist (defaults to current)

### Feed Recovery

- `ACE_RETRY_FEED` — retry failed feed after clearing obstruction (see [FEED_RECOVERY_GUIDE.md](./FEED_RECOVERY_GUIDE.md))
- `ACE_CANCEL_FEED` — cancel failed feed and abort print

### Configuration

- `ACE_GATE_MAP GATE=<n> [DEVICE=<id|alias>] [COLOR=<hexRGB>] [TYPE=<material>] [TEMP=<°C>]` — set gate metadata
- `ACE_ENDLESS_SPOOL [ENABLE=<0|1>]` — toggle endless spool (no argument shows status)

### Status & Diagnostics

- `ACE_GET_STATUS [DEVICE=<id|alias|index>] [VERBOSE=<0|1>]` — display system status
- `ACE_SCAN_DEVICES [APPLY=<0|1>] [VERBOSE=<0|1>]` — scan USB for ACE devices
- `ACE_LIST_DEVICES` — list connected ACE devices with connection info
- `ACE_SHOW_USB_INFO` — display USB topology and device mapping
- `ACE_DEBUG METHOD=<json_rpc_method> [PARAMS=’{"k":"v"}’] [DEVICE=<id|index>]` — send raw commands to ACE

### Dryer Control

- `ACE_START_DRYING TEMP=<°C> [DURATION=<min>] DEVICE=<id|alias>|GATE=<n>` — start dryer (default 240 min; limited by `max_dryer_temperature`)
- `ACE_STOP_DRYING DEVICE=<id|alias>|GATE=<n>` — stop dryer
- `ACE_GET_DRYER_STATUS` — display all dryer statuses (see [DRYER_CONTROL_GUIDE.md](./DRYER_CONTROL_GUIDE.md))

### Device Aliasing

- `ACE_ALIAS DEVICE=<id> NAME=<alias>` — set friendly device alias
- `ACE_UNALIAS DEVICE=<id_or_alias>` — remove device alias
- `ACE_LIST_ALIASES` — list all device aliases (see [DEVICE_ALIASING_GUIDE.md](./DEVICE_ALIASING_GUIDE.md))

## 🧲 Sensors and Logic

Two filament presence sensors are used:

- `extruder_sensor` — at the extruder (required for proper operation)
- `toolhead_sensor` — at the toolhead (optional for fine tuning up to the nozzle)

## 🧪 Typical Workflow

- Tune `POOP` and `CUT_TIP` macros for your printer.
- During printing use `T0..T3` or `ACE_CHANGE_TOOL TOOL=N`.
- For drying: `ACE_START_DRYING TEMP=55 DURATION=180`, stop — `ACE_STOP_DRYING`.

## 🔌 Pinout and Wiring

<img src="./.github/img/pinout.png" alt="drawing" width="500"/>

Important: VCC (24 V) for logic is not required — ACE powers itself. Connect via USB to a regular port.

## 🐞 Debug and Logs

- In Klipper console look for messages starting with `ACE:` — statuses/errors.
- If there’s no connection — check `serial` (/dev/serial/by-id/… or /dev/tty…) and device permissions.
- For low-level communication testing use `ACE_DEBUG`.

## 🗺️ Roadmap

- [ ] UI panel/card in Mainsail/Fluidd (dryer control, gate mapping)
- [ ] Auto-detect `serial` by ACE VID/PID
- [ ] Material presets for quick select (PLA/PETG/ABS, etc.)
- [ ] Docs for integration with popular slicer profiles
- [ ] Tests and CI for stability

## 📜 License

See [LICENSE.md](./LICENSE.md)

## 👥 Authors and Contributors

- A place for authors list and acknowledgements 🙏
- PRs are welcome! Describe changes and follow commit style.
- PRs are welcome! Describe changes and follow commit style.
