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
  echo -n "Copy config file to Klipper... "
  echo -n "[WARNING] If you have custom [save_variables], you must place the ace_vars.cfg data in your vars file and comment out [save_variables] in ace.cfg"
  if [ ! -f "${KLIPPER_CONFIG_HOME}/ace.cfg" ]; then
      cat "${SRCDIR}/ace.cfg" | sed -e "s|{config_path}|${KLIPPER_CONFIG_HOME}|g" > ace.cfg.tmp
      mv ace.cfg.tmp "${KLIPPER_CONFIG_HOME}/ace.cfg"
      cp ace_vars.cfg "${KLIPPER_CONFIG_HOME}/ace_vars.cfg"
      echo "[OK]"
  else
      echo "[SKIPPED]"
  fi
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
    if [ -f "${KLIPPER_HOME}/klippy/extras/ace.py" ]; then
        echo -n "Uninstalling Klipper extension... "
        rm -f "${KLIPPER_HOME}/klippy/extras/ace.py"
        echo "[OK]"
    else
        echo "ace.py not found in \"${KLIPPER_HOME}/klippy/extras/\". Is it installed?"
    fi

    # Uninstall Moonraker component
    if [ -f "${MOONRAKER_HOME}/moonraker/components/ace_manager.py" ]; then
        echo -n "Uninstalling Moonraker component... "
        rm -f "${MOONRAKER_HOME}/moonraker/components/ace_manager.py"
        echo "[OK]"
        echo "[INFO] Remember to remove the [ace_manager] section from moonraker.conf"
    else
        echo "ace_manager.py not found in Moonraker components"
    fi

    echo ""
    echo "Uninstall complete!"
    echo "You can now:"
    echo "  - Remove the [update_manager BunnyACE] section from moonraker.conf"
    echo "  - Remove the [ace_manager] section from moonraker.conf"
    echo "  - Remove ACE configuration from printer.cfg"
    echo "  - Delete this directory"
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
    echo "1. Add ACE configuration to printer.cfg (see ace.cfg for example)"
    echo "2. Restart Klipper and Moonraker"
    echo "3. Test with: ACE_LIST_DEVICES"
    echo ""
    if [ "$MOONRAKER_INSTALL" -eq 1 ]; then
        echo "ACE Manager REST API is available at:"
        echo "  - GET  http://localhost:7125/server/ace/devices"
        echo "  - GET  http://localhost:7125/server/ace/status"
        echo "  - POST http://localhost:7125/server/ace/scan"
        echo ""
    fi
else
    uninstall
fi

start_klipper
