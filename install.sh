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
    echo -n "Linking extension to Klipper... "
    ln -sf "${SRCDIR}/extras/ace.py" "${KLIPPER_HOME}/klippy/extras/ace.py"
    echo "[OK]"
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

    # Uninstall Klipper extension
    if [ -f "${KLIPPER_HOME}/klippy/extras/ace.py" ]; then
        echo -n "  - Removing Klipper extension... "
        rm -f "${KLIPPER_HOME}/klippy/extras/ace.py"
        echo "[OK]"
    else
        echo "  - ace.py not found in Klipper extras [SKIPPED]"
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
    if [ "$MOONRAKER_INSTALL" -eq 1 ]; then
        echo "ACE Manager REST API is available at:"
        echo "  - GET  http://localhost:7125/server/ace/devices"
        echo "  - GET  http://localhost:7125/server/ace/status"
        echo "  - POST http://localhost:7125/server/ace/scan"
        echo ""
    fi
    echo "Documentation:"
    echo "  - USB_PORT_MAPPING_GUIDE.md  - USB port-based device mapping"
    echo "  - DRYER_CONTROL_GUIDE.md     - Per-device dryer control"
    echo "  - MIGRATION_GUIDE.md         - Fixing corrupted ace_vars.cfg"
    echo ""
else
    uninstall
fi

start_klipper
