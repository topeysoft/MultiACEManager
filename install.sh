#!/bin/sh
IS_MIPS=0
if [ "$(uname -m)" = "mips" ]; then
   IS_MIPS=1
fi

KLIPPER_HOME="${HOME}/klipper"
KLIPPER_ENV="${HOME}/klippy-env"
KLIPPER_CONFIG_HOME="${HOME}/printer_data/config"
MOONRAKER_CONFIG_DIR="${HOME}/printer_data/config"
MOONRAKER_HOME="${HOME}/moonraker"
SRCDIR="$PWD"


if [ "$IS_MIPS" -eq 1 ]; then
    KLIPPER_HOME="/usr/share/klipper"
    KLIPPER_ENV="/usr/share/klippy-env"
    KLIPPER_CONFIG_HOME="/usr/data/printer_data/config"
    MOONRAKER_CONFIG_DIR="/usr/data/printer_data/config"
    MOONRAKER_HOME="/usr/share/moonraker"
fi

usage(){ echo "Usage: $0 [-u]" 1>&2; exit 1; }
# Parse command line arguments
UNINSTALL=0
while getopts "uh" arg; do
   case $arg in
       u) UNINSTALL=1;;
       h) usage;;
   esac
done

verify_ready()
{
  if [ "$IS_MIPS" -ne 1 ]; then
    if [ "$EUID" -eq 0 ]; then
        echo "[ERROR] This script must not run as root. Exiting."
        exit 1
    fi
  else
    echo -e "[WARNING] This script is running on a MIPS system, so we expect it to be run as root"
  fi
}

check_folders()
{
    if [ ! -d "$KLIPPER_HOME/klippy/extras/" ]; then
        echo "[ERROR] Klipper installation not found in directory \"$KLIPPER_HOME\". Exiting"
        exit 1
    fi
    echo "Klipper installation found at $KLIPPER_HOME"

    if [ ! -d "${KLIPPER_CONFIG_HOME}/" ]; then
        echo "[ERROR] Klipper configs not found in directory \"$MOONRAKER_CONFIG_DIR\". Exiting"
        exit 1
    fi
    echo "Klipper config directory found at $KLIPPER_CONFIG_HOME"

    if [ ! -f "${MOONRAKER_CONFIG_DIR}/moonraker.conf" ]; then
        echo "[ERROR] Moonraker configuration not found in directory \"$MOONRAKER_CONFIG_DIR\". Exiting"
        exit 1
    fi
    echo "Moonraker configuration found at $MOONRAKER_CONFIG_DIR"

    if [ ! -d "${MOONRAKER_HOME}/moonraker/components/" ]; then
        echo "[WARNING] Moonraker components directory not found at \"${MOONRAKER_HOME}/moonraker/components/\""
        echo "[WARNING] ACE Manager Moonraker component will not be installed"
        MOONRAKER_INSTALL=0
    else
        echo "Moonraker installation found at $MOONRAKER_HOME"
        MOONRAKER_INSTALL=1
    fi
}

link_extension()
{
    echo "Linking ACE modular architecture to Klipper..."

    # Create ace package directory structure
    echo -n "  - Creating ace package directory... "
    mkdir -p "${KLIPPER_HOME}/klippy/extras/ace"
    echo "[OK]"

    # Link modular architecture files
    echo -n "  - Linking ace/__init__.py (entry point)... "
    ln -sf "${SRCDIR}/extras/__init__.py" "${KLIPPER_HOME}/klippy/extras/ace/__init__.py"
    echo "[OK]"

    echo -n "  - Linking ace/exceptions.py... "
    ln -sf "${SRCDIR}/extras/exceptions.py" "${KLIPPER_HOME}/klippy/extras/ace/exceptions.py"
    echo "[OK]"

    echo -n "  - Linking ace/ace_controller.py... "
    ln -sf "${SRCDIR}/extras/ace_controller.py" "${KLIPPER_HOME}/klippy/extras/ace/ace_controller.py"
    echo "[OK]"

    # Link protocol package
    echo -n "  - Creating ace/protocol directory... "
    mkdir -p "${KLIPPER_HOME}/klippy/extras/ace/protocol"
    echo "[OK]"

    ln -sf "${SRCDIR}/extras/protocol/__init__.py" "${KLIPPER_HOME}/klippy/extras/ace/protocol/__init__.py"
    ln -sf "${SRCDIR}/extras/protocol/constants.py" "${KLIPPER_HOME}/klippy/extras/ace/protocol/constants.py"
    ln -sf "${SRCDIR}/extras/protocol/packet.py" "${KLIPPER_HOME}/klippy/extras/ace/protocol/packet.py"
    echo -n "  - Linked protocol/*.py (3 files)... "
    echo "[OK]"

    # Link device package
    echo -n "  - Creating ace/device directory... "
    mkdir -p "${KLIPPER_HOME}/klippy/extras/ace/device"
    echo "[OK]"

    ln -sf "${SRCDIR}/extras/device/__init__.py" "${KLIPPER_HOME}/klippy/extras/ace/device/__init__.py"
    ln -sf "${SRCDIR}/extras/device/ace_device.py" "${KLIPPER_HOME}/klippy/extras/ace/device/ace_device.py"
    ln -sf "${SRCDIR}/extras/device/device_manager.py" "${KLIPPER_HOME}/klippy/extras/ace/device/device_manager.py"
    ln -sf "${SRCDIR}/extras/device/device_discovery.py" "${KLIPPER_HOME}/klippy/extras/ace/device/device_discovery.py"
    ln -sf "${SRCDIR}/extras/device/device_mapper.py" "${KLIPPER_HOME}/klippy/extras/ace/device/device_mapper.py"
    echo -n "  - Linked device/*.py (5 files)... "
    echo "[OK]"

    # Link sensors package
    echo -n "  - Creating ace/sensors directory... "
    mkdir -p "${KLIPPER_HOME}/klippy/extras/ace/sensors"
    echo "[OK]"

    ln -sf "${SRCDIR}/extras/sensors/__init__.py" "${KLIPPER_HOME}/klippy/extras/ace/sensors/__init__.py"
    ln -sf "${SRCDIR}/extras/sensors/runout_helper.py" "${KLIPPER_HOME}/klippy/extras/ace/sensors/runout_helper.py"
    echo -n "  - Linked sensors/*.py (2 files)... "
    echo "[OK]"

    # Link commands package
    echo -n "  - Creating ace/commands directory... "
    mkdir -p "${KLIPPER_HOME}/klippy/extras/ace/commands"
    echo "[OK]"

    ln -sf "${SRCDIR}/extras/commands/__init__.py" "${KLIPPER_HOME}/klippy/extras/ace/commands/__init__.py"
    ln -sf "${SRCDIR}/extras/commands/tool_commands.py" "${KLIPPER_HOME}/klippy/extras/ace/commands/tool_commands.py"
    ln -sf "${SRCDIR}/extras/commands/config_commands.py" "${KLIPPER_HOME}/klippy/extras/ace/commands/config_commands.py"
    ln -sf "${SRCDIR}/extras/commands/status_commands.py" "${KLIPPER_HOME}/klippy/extras/ace/commands/status_commands.py"
    echo -n "  - Linked commands/*.py (4 files)... "
    echo "[OK]"

    echo ""
    echo "================================================"
    echo "ACE Modular Architecture Installed!"
    echo "================================================"
    echo "  Total: 18 modular files"
    echo "  Entry: ace/__init__.py:load_config()"
    echo "  Architecture: AceController → AceDeviceManager → AceDevice"
    echo ""
}

copy_config()
{
  echo -n "Copying config files to Klipper config directory... "
  echo ""

  # Copy ace.cfg if it doesn't exist
  if [ ! -f "${KLIPPER_CONFIG_HOME}/ace.cfg" ]; then
      echo "  - Installing ace.cfg"
      cat "${SRCDIR}/ace.cfg" | sed -e "s|{config_path}|${KLIPPER_CONFIG_HOME}|g" > ace.cfg.tmp
      mv ace.cfg.tmp "${KLIPPER_CONFIG_HOME}/ace.cfg"
  else
      echo "  - ace.cfg already exists [SKIPPED]"
  fi

  # Copy ace_vars.cfg if it doesn't exist (or backup if corrupted)
  if [ ! -f "${KLIPPER_CONFIG_HOME}/ace_vars.cfg" ]; then
      echo "  - Installing ace_vars.cfg"
      cp "${SRCDIR}/ace_vars.cfg" "${KLIPPER_CONFIG_HOME}/ace_vars.cfg"
  else
      echo "  - ace_vars.cfg already exists [SKIPPED]"
      echo "    [INFO] If experiencing DuplicateOptionError, see MIGRATION_GUIDE.md"
  fi

  # Copy dryer macros if they don't exist
  if [ ! -f "${KLIPPER_CONFIG_HOME}/ace_dryer_macros.cfg" ]; then
      echo "  - Installing ace_dryer_macros.cfg"
      cp "${SRCDIR}/ace_dryer_macros.cfg" "${KLIPPER_CONFIG_HOME}/ace_dryer_macros.cfg"
      echo "    [INFO] To use dryer macros, add to printer.cfg:"
      echo "    [include ace_dryer_macros.cfg]"
  else
      echo "  - ace_dryer_macros.cfg already exists [SKIPPED]"
  fi

  # Copy example auto-detect config
  if [ ! -f "${KLIPPER_CONFIG_HOME}/ace_manager_auto_detect.cfg" ]; then
      echo "  - Installing ace_manager_auto_detect.cfg (example config)"
      cp "${SRCDIR}/ace_manager_auto_detect.cfg" "${KLIPPER_CONFIG_HOME}/ace_manager_auto_detect.cfg"
      echo "    [INFO] This is a reference config, not automatically included"
  else
      echo "  - ace_manager_auto_detect.cfg already exists [SKIPPED]"
  fi

  echo "[OK]"
  echo ""
  echo "[WARNING] If you have custom [save_variables], you must:"
  echo "  1. Copy ace_vars.cfg content to your custom vars file"
  echo "  2. Comment out [save_variables] in ace.cfg"
}

install_moonraker_component()
{
    if [ "$MOONRAKER_INSTALL" -eq 1 ]; then
        echo -n "Installing ACE Manager Moonraker component... "
        if [ -f "${SRCDIR}/moonraker/ace_manager.py" ]; then
            ln -sf "${SRCDIR}/moonraker/ace_manager.py" "${MOONRAKER_HOME}/moonraker/components/ace_manager.py"
            echo "[OK]"

            # Check if [ace_manager] section exists in moonraker.conf
            ace_section=$(grep -c '\[ace_manager\]' "${MOONRAKER_CONFIG_DIR}/moonraker.conf" || true)
            if [ "$ace_section" -eq 0 ]; then
                echo -n "Adding [ace_manager] to moonraker.conf... "
                echo "" >> "${MOONRAKER_CONFIG_DIR}/moonraker.conf"
                echo "# ACE Manager REST API component" >> "${MOONRAKER_CONFIG_DIR}/moonraker.conf"
                echo "[ace_manager]" >> "${MOONRAKER_CONFIG_DIR}/moonraker.conf"
                echo "" >> "${MOONRAKER_CONFIG_DIR}/moonraker.conf"
                echo "[OK]"
            else
                echo "[ace_manager] section already exists in moonraker.conf [SKIPPED]"
            fi
        else
            echo "[ERROR] ace_manager.py not found in ${SRCDIR}/moonraker/"
            echo "[FAILED]"
        fi
    else
        echo "Moonraker component installation skipped (Moonraker not found)"
    fi
}

install_requirements()
{
    echo -n "Install requirements... "
    "${KLIPPER_ENV}/bin/pip" install -r "${SRCDIR}/requirements.txt"
    echo "[OK]"
}

uninstall()
{
    echo "Uninstalling BunnyACE..."
    echo ""

    # Uninstall ACE package (contains both legacy and modular)
    if [ -d "${KLIPPER_HOME}/klippy/extras/ace" ]; then
        echo -n "  - Removing ace/ package (legacy + modular)... "
        rm -rf "${KLIPPER_HOME}/klippy/extras/ace"
        echo "[OK]"
    else
        echo "  - ace/ package not found [SKIPPED]"
    fi

    # Remove old standalone ace.py if it exists (from previous installations)
    if [ -f "${KLIPPER_HOME}/klippy/extras/ace.py" ]; then
        echo -n "  - Removing old ace.py (if exists from previous install)... "
        rm -f "${KLIPPER_HOME}/klippy/extras/ace.py"
        echo "[OK]"
    fi

    # Uninstall Moonraker component
    if [ -f "${MOONRAKER_HOME}/moonraker/components/ace_manager.py" ]; then
        echo -n "  - Removing Moonraker component... "
        rm -f "${MOONRAKER_HOME}/moonraker/components/ace_manager.py"
        echo "[OK]"
    else
        echo "  - ace_manager.py not found in Moonraker components [SKIPPED]"
    fi

    # Ask about config files
    echo ""
    echo "Config files found in ${KLIPPER_CONFIG_HOME}:"
    config_files=0
    [ -f "${KLIPPER_CONFIG_HOME}/ace.cfg" ] && echo "  - ace.cfg" && config_files=1
    [ -f "${KLIPPER_CONFIG_HOME}/ace_vars.cfg" ] && echo "  - ace_vars.cfg" && config_files=1
    [ -f "${KLIPPER_CONFIG_HOME}/ace_dryer_macros.cfg" ] && echo "  - ace_dryer_macros.cfg" && config_files=1
    [ -f "${KLIPPER_CONFIG_HOME}/ace_device_map.cfg" ] && echo "  - ace_device_map.cfg" && config_files=1
    [ -f "${KLIPPER_CONFIG_HOME}/ace_manager_auto_detect.cfg" ] && echo "  - ace_manager_auto_detect.cfg" && config_files=1

    if [ "$config_files" -eq 1 ]; then
        echo ""
        echo "These config files contain your settings and will NOT be automatically removed."
        echo "To remove them manually:"
        echo "  rm ${KLIPPER_CONFIG_HOME}/ace*.cfg"
    else
        echo "  (none found)"
    fi

    echo ""
    echo "========================================="
    echo "Uninstall Complete!"
    echo "========================================="
    echo ""
    echo "Manual cleanup required:"
    echo "  1. Remove [update_manager BunnyACE] from moonraker.conf"
    echo "  2. Remove [ace_manager] from moonraker.conf"
    echo "  3. Remove ACE configuration from printer.cfg"
    echo "  4. Optionally remove config files (see above)"
    echo "  5. Delete this directory: rm -rf ${SRCDIR}"
    echo ""
}

restart_moonraker()
{
    echo -n "Restarting Moonraker... "
    sudo systemctl restart moonraker
    sleep 1
    echo "[OK]"
}

start_moonraker() {
  echo -n "Starting Moonraker... "
  /etc/init.d/S56moonraker_service start
  sleep 1
  echo "[OK]"
}

stop_moonraker() {
  echo -n "Stopping Moonraker... "
  /etc/init.d/S56moonraker_service stop
  sleep 1
  echo "[OK]"
}

start_klipper() {
  echo -n "Starting Klipper... "
  if [ "$IS_MIPS" -eq 1 ]; then
    /etc/init.d/S55klipper_service start
  else
    sudo systemctl start klipper
  fi
  echo "[OK]"
}


stop_klipper() {
  echo -n "Stopping Klipper... "
  if [ "$IS_MIPS" -eq 1 ]; then
    /etc/init.d/S55klipper_service stop
  else
    sudo systemctl stop klipper
  fi
  echo "[OK]"
}

setup_device_aliases()
{
    echo ""
    echo "========================================="
    echo "Device Alias Setup (Optional)"
    echo "========================================="
    echo ""
    echo "You can assign friendly aliases to your ACE devices"
    echo "Examples: ACE1, ACE2, top_left, filament_tower, etc."
    echo ""
    echo "Would you like to set up device aliases now? (y/n)"
    read -r response

    if [ "$response" != "y" ] && [ "$response" != "Y" ]; then
        echo "Skipping alias setup. You can set aliases later using:"
        echo "  ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE1"
        return
    fi

    echo ""
    echo "Choose naming scheme:"
    echo "  1) Sequential (ACE1, ACE2, ACE3, ...)"
    echo "  2) Positional (top_left, top_right, bottom_left, bottom_right)"
    echo "  3) Custom (you choose each name)"
    echo "  4) Skip"
    echo ""
    echo -n "Enter choice (1-4): "
    read -r naming_choice

    # Create device map config if it doesn't exist
    DEVICE_MAP_FILE="${KLIPPER_CONFIG_HOME}/ace_device_map.cfg"
    if [ ! -f "$DEVICE_MAP_FILE" ]; then
        echo "# Auto-generated by ACE Manager - DO NOT EDIT MANUALLY" > "$DEVICE_MAP_FILE"
        echo "# This file stores device properties by USB port location" >> "$DEVICE_MAP_FILE"
        echo "" >> "$DEVICE_MAP_FILE"
        echo "[ace_device_map]" >> "$DEVICE_MAP_FILE"
    fi

    case $naming_choice in
        1)
            echo ""
            echo "Using sequential naming (ACE1, ACE2, ACE3, ...)"
            echo "After Klipper starts, run these commands to set aliases:"
            echo "  ACE_SCAN_DEVICES"
            echo "  Then for each device:"
            echo "  ACE_ALIAS DEVICE=hub_1_port_X NAME=ACE1"
            echo "  ACE_ALIAS DEVICE=hub_1_port_Y NAME=ACE2"
            echo "  etc."
            ;;
        2)
            echo ""
            echo "Using positional naming"
            echo "After Klipper starts, map your devices:"
            echo "  ACE_ALIAS DEVICE=hub_1_port_1 NAME=top_left"
            echo "  ACE_ALIAS DEVICE=hub_1_port_2 NAME=top_right"
            echo "  ACE_ALIAS DEVICE=hub_1_port_3 NAME=bottom_left"
            echo "  ACE_ALIAS DEVICE=hub_1_port_4 NAME=bottom_right"
            ;;
        3)
            echo ""
            echo "After Klipper starts, use ACE_SHOW_USB_INFO to see devices"
            echo "Then set custom aliases with:"
            echo "  ACE_ALIAS DEVICE=hub_1_port_X NAME=your_custom_name"
            ;;
        *)
            echo "Skipping alias setup"
            ;;
    esac
}

add_updater()
{
    echo -n "Adding update manager to moonraker.conf... "
    update_section=0
    update_section=$(grep -c '\[update_manager[a-z ]* BunnyACE\]' "${MOONRAKER_CONFIG_DIR}/moonraker.conf" || true)
    if [ "$update_section" -eq 0 ]; then
        echo "\n" >> ${MOONRAKER_CONFIG_DIR}/moonraker.conf
        while read -r line; do
            echo "${line}" >> ${MOONRAKER_CONFIG_DIR}/moonraker.conf
        done < "${SRCDIR}/templates/moonraker_update.txt"
        echo "\n" >> ${MOONRAKER_CONFIG_DIR}/moonraker.conf
        echo "[OK]"

        if [ "$IS_MIPS" -eq 1 ]; then
          stop_moonraker
          start_moonraker
        else
          restart_moonraker
        fi
    else
        echo "[SKIPPED]"
    fi

}


verify_ready
check_folders
stop_klipper

if [ "$UNINSTALL" -ne 1 ]; then
    link_extension
    copy_config
    install_moonraker_component
    add_updater
    setup_device_aliases

    echo ""
    echo "========================================="
    echo "Installation Complete!"
    echo "========================================="
    echo ""
    echo "Next steps:"
    echo "1. Add ACE configuration to printer.cfg"
    echo "   For auto-detect: [include ace_manager_auto_detect.cfg]"
    echo "   Or see ace.cfg for manual configuration"
    echo ""
    echo "2. (Optional) Enable dryer macros in printer.cfg:"
    echo "   [include ace_dryer_macros.cfg]"
    echo ""
    echo "3. Restart Klipper and Moonraker"
    echo "   sudo systemctl restart klipper moonraker"
    echo ""
    echo "4. Test with diagnostic commands:"
    echo "   ACE_LIST_DEVICES      - Show all ACE devices"
    echo "   ACE_SHOW_USB_INFO     - Show USB topology and mapping"
    echo "   ACE_GET_DRYER_STATUS  - Show dryer status for all devices"
    echo ""
    echo "5. Device Aliasing:"
    echo "   ACE_ALIAS DEVICE=hub_1_port_2 NAME=ACE1    - Set alias"
    echo "   ACE_UNALIAS DEVICE=ACE1                    - Remove alias"
    echo "   Then use aliases in commands:"
    echo "   ACE_GET_STATUS DEVICE=ACE1"
    echo ""
    if [ "$MOONRAKER_INSTALL" -eq 1 ]; then
        echo "ACE Manager REST API is available at:"
        echo "  - GET  http://localhost:7125/server/ace/devices"
        echo "  - GET  http://localhost:7125/server/ace/status"
        echo "  - POST http://localhost:7125/server/ace/scan"
        echo ""
    fi
    echo "Documentation:"
    echo "  - extras/ARCHITECTURE.md     - Modular architecture details"
    echo "  - USB_PORT_MAPPING_GUIDE.md  - USB port-based device mapping"
    echo "  - DRYER_CONTROL_GUIDE.md     - Per-device dryer control"
    echo ""
else
    uninstall
fi

start_klipper
