# KlipperACE Device Aliasing Guide

## Overview

KlipperACE supports friendly device aliases, allowing you to reference devices by human-readable names instead of technical USB port identifiers.

## Features

- **Flexible Naming**: Use any alphanumeric name with underscores (e.g., `ACE1`, `top_left`, `filament_tower`)
- **Persistent Storage**: Aliases are stored in `ace_device_map.cfg` and persist across reboots
- **Universal Usage**: Use aliases anywhere you would use a device ID
- **Easy Management**: Simple commands to set and remove aliases

## Quick Start

### 1. View Your Devices

First, see what devices are connected and their IDs:

```gcode
ACE_SHOW_USB_INFO
```

Output example:

```
======================================================================
ACE USB Port Mapping & Device Topology
======================================================================

Currently Connected Devices:
----------------------------------------------------------------------

✓ Device 1: ACE_1
   ID:           hub_1_port_2
   USB Location: 1-1.2
   Serial Port:  /dev/ttyACM0
   Gate Range:   0-3

✓ Device 2: ACE_2
   ID:           hub_1_port_3
   USB Location: 1-1.3
   Serial Port:  /dev/ttyACM1
   Gate Range:   4-7
```

### 2. Set Aliases

Assign friendly names to your devices:

```gcode
ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE1
ACE_ALIAS DEVICE=hub_1_port_3 NAME=top_left
```

### 3. Use Aliases

Now use your aliases in any command:

```gcode
ACE_GET_STATUS DEVICE=ACE1
ACE_GATE_MAP DEVICE=top_left GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
ACE_LIST_DEVICES
```

## Commands

### ACE_ALIAS

Set or update a device alias.

**Syntax:**

```gcode
ACE_ALIAS DEVICE=<device_id_or_alias> NAME=<new_alias>
```

**Parameters:**

- `DEVICE`: The device ID (e.g., `hub_1_port_2`) or existing alias
- `NAME`: The new alias (alphanumeric and underscore only)

**Examples:**

```gcode
ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE1
ACE_ALIAS DEVICE=hub_1_port_3 NAME=top_left
ACE_ALIAS DEVICE=hub_1_port_4 NAME=filament_tower
ACE_ALIAS DEVICE=ACE1 NAME=front_unit  # Change existing alias
```

### ACE_UNALIAS

Remove an alias from a device.

**Syntax:**

```gcode
ACE_UNALIAS DEVICE=<device_id_or_alias>
```

**Examples:**

```gcode
ACE_UNALIAS DEVICE=ACE1
ACE_UNALIAS DEVICE=hub_1_port_2
```

### ACE_LIST_ALIASES

List all defined device aliases with their connection status.

**Syntax:**

```gcode
ACE_LIST_ALIASES
```

**Example output:**

```
======================================================================
Device Aliases
======================================================================

  ACE1                 → hub_1_port_2       (✓ Connected, Gates 0-3)
  top_left             → hub_1_port_3       (✓ Connected, Gates 4-7)
  filament_tower       → hub_1_port_4       (⊗ Disconnected)

======================================================================
Total: 3 aliases defined
======================================================================
```

**Use cases:**

- Check what aliases you've set
- See connection status of aliased devices
- Verify alias names before using them in commands
- Quick reference when writing macros

## Common Naming Schemes

### Sequential Naming

Simple numbering scheme:

```gcode
ACE_ALIAS DEVICE=hub_1_port_1 NAME=ACE1
ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE2
ACE_ALIAS DEVICE=hub_1_port_3 NAME=ACE3
ACE_ALIAS DEVICE=hub_1_port_4 NAME=ACE4
```

### Positional Naming

Based on physical location:

```gcode
ACE_ALIAS DEVICE=hub_1_port_1 NAME=top_left
ACE_ALIAS DEVICE=hub_1_port_2 NAME=top_right
ACE_ALIAS DEVICE=hub_1_port_3 NAME=bottom_left
ACE_ALIAS DEVICE=hub_1_port_4 NAME=bottom_right
```

### Descriptive Naming

Based on function or location:

```gcode
ACE_ALIAS DEVICE=hub_1_port_1 NAME=main_tower
ACE_ALIAS DEVICE=hub_1_port_2 NAME=support_materials
ACE_ALIAS DEVICE=hub_1_port_3 NAME=specialty_filaments
```

## Using Aliases in Commands

Once set, aliases work everywhere a device ID would:

### Status Commands

```gcode
ACE_GET_STATUS DEVICE=ACE1
ACE_LIST_DEVICES  # Shows aliases in output
ACE_SHOW_USB_INFO # Displays aliases prominently
```

### Configuration Commands

```gcode
# Device-relative gates (GATE 0-3 per device)
ACE_GATE_MAP DEVICE=top_left GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
ACE_GATE_MAP DEVICE=ACE1 GATE=1 COLOR=00FF00 TYPE=PETG TEMP=240

# Global gates (without DEVICE parameter)
ACE_GATE_MAP GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210   # Gate 0 globally
ACE_GATE_MAP GATE=5 COLOR=0000FF TYPE=ABS TEMP=250   # Gate 5 globally
```

**Important:** When using `DEVICE` parameter with `ACE_GATE_MAP`:

- `GATE` is **relative to the device** (0-3)
- Without `DEVICE`, `GATE` is **global** (0-N where N = total gates - 1)

Example with 2 devices:

- `ACE_GATE_MAP DEVICE=ACE1 GATE=0` → Configures global gate 0 (first gate on ACE1)
- `ACE_GATE_MAP DEVICE=ACE2 GATE=0` → Configures global gate 4 (first gate on ACE2)
- `ACE_GATE_MAP GATE=5` → Configures global gate 5 (second gate on ACE2)

## Installation Setup

During installation, you can optionally set up aliases:

```bash
./install.sh
```

The installer will ask if you want to configure device aliases and offer preset naming schemes:

1. Sequential (ACE1, ACE2, ACE3, ...)
2. Positional (top_left, top_right, bottom_left, bottom_right)
3. Custom (you choose each name)
4. Skip (configure later)

## Storage

Aliases are stored in `ace_device_map.cfg` alongside device properties:

```ini
[ace_device_map]
hub_1_port_2 = /dev/ttyACM0, 0, 1732723456, 1-1.2, ACE1
hub_1_port_3 = /dev/ttyACM1, 4, 1732723456, 1-1.3, top_left
```

Format: `device_id = port, gate_offset, timestamp, usb_location, alias`

## Technical Details

### Alias Resolution

The system resolves aliases in the following order:

1. Check if input is an alias → resolve to device_id
2. Check if input is a device_id → use directly
3. Not found → error

### Alias Validation

Aliases must:

- Be unique (no two devices can have the same alias)
- Contain only letters, numbers, and underscores
- Not be empty

### Persistence

- Aliases persist across reboots
- Aliases follow the physical device (USB port)
- If a device is moved to a different USB port, it keeps its alias
- If a device is disconnected, its alias is preserved for when it reconnects

## Examples

### Complete Setup Example

```gcode
# 1. View devices
ACE_SHOW_USB_INFO

# 2. Set aliases
ACE_ALIAS DEVICE=hub_1_port_1 NAME=ACE1
ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE2

# 3. Configure gates using aliases
ACE_GATE_MAP DEVICE=ACE1 GATE=0 COLOR=FF0000 TYPE=PLA TEMP=210
ACE_GATE_MAP DEVICE=ACE1 GATE=1 COLOR=00FF00 TYPE=PETG TEMP=240
ACE_GATE_MAP DEVICE=ACE2 GATE=0 COLOR=0000FF TYPE=ABS TEMP=250

# 4. List all aliases
ACE_LIST_ALIASES

# 5. Check status with aliases
ACE_GET_STATUS DEVICE=ACE1
ACE_LIST_DEVICES
```

### Renaming a Device

```gcode
# Change ACE1 to main_unit
ACE_ALIAS DEVICE=ACE1 NAME=main_unit

# Verify the change
ACE_LIST_ALIASES

# Or remove alias entirely
ACE_UNALIAS DEVICE=main_unit
```

### Managing Multiple Aliases

```gcode
# Set up all your devices
ACE_ALIAS DEVICE=hub_1_port_1 NAME=ACE1
ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE2
ACE_ALIAS DEVICE=hub_1_port_3 NAME=ACE3
ACE_ALIAS DEVICE=hub_1_port_4 NAME=ACE4

# View all aliases at once
ACE_LIST_ALIASES

# Update a specific one
ACE_ALIAS DEVICE=ACE3 NAME=specialty_materials

# Check the updated list
ACE_LIST_ALIASES
```

## Benefits

1. **Easier Identification**: "ACE1" is easier to remember than "hub_1_port_2"
2. **Self-Documenting**: Positional names (top_left) make physical layout clear
3. **Flexible**: Change aliases anytime without affecting device properties
4. **Consistent**: Aliases work everywhere device IDs work
5. **Persistent**: Aliases survive reboots and device reconnections

## Best Practices

1. **Use Consistent Naming**: Pick a scheme (sequential, positional, descriptive) and stick with it
2. **Document Your Layout**: Keep notes on which USB port corresponds to which physical location
3. **Label Physical Devices**: Put labels on your ACE units matching their aliases
4. **Set Aliases Early**: Configure aliases during initial setup for easier management
5. **Keep It Simple**: Short, memorable aliases are easier to use

## Troubleshooting

### Alias Already in Use

```
Error: Alias 'ACE1' already in use by device hub_1_port_2
```

**Solution**: Choose a different alias or remove the existing one first with `ACE_UNALIAS`

### Device Not Found

```
Error: Device "ACE1" not found
```

**Solution**: Check device is connected with `ACE_LIST_DEVICES` or `ACE_SHOW_USB_INFO`

### Invalid Alias Format

```
Error: Alias must contain only letters, numbers, and underscores
```

**Solution**: Use only alphanumeric characters and underscores (no spaces, hyphens, or special characters)

## See Also

- [USB_PORT_MAPPING_GUIDE.md](USB_PORT_MAPPING_GUIDE.md) - USB port-based device mapping
- [ARCHITECTURE.md](extras/ARCHITECTURE.md) - System architecture
- [README.md](README.md) - Main documentation
