#!/bin/bash
#
# Deploy KlipperACE to a printer SBC and restart Klipper.
#
# Usage:
#   ./deploy.sh <printer>          # deploy and restart
#   ./deploy.sh <printer> --dry    # preview what would sync (no changes)
#   ./deploy.sh <printer> --log    # deploy, restart, and tail log
#
# Examples:
#   ./deploy.sh obi1
#   ./deploy.sh r2d2 --log
#   ./deploy.sh obi1 --dry
# where the printer names (obi1, r2d2, c3po) are defined in the resolve_printer() function below.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SBC_USER="${SBC_USER:-pi}"

# --- Printer registry ---
# Add your printers here: name -> hostname
resolve_printer() {
    case "$1" in
        obi1) echo "obi1.local" ;;
        r2d2) echo "r2d2.local" ;;
        c3po) echo "c3po.local" ;;
        *)    return 1 ;;
    esac
}

AVAILABLE_PRINTERS="obi1 r2d2 c3po"

# --- Remote paths (standard Klipper install) ---
REMOTE_ACE_DIR="~/klipper/klippy/extras/ace"
REMOTE_MOONRAKER_COMPONENT="~/moonraker/moonraker/components/ace_manager.py"

# ------------------------------------------------------------------

usage() {
    echo "Usage: $0 <printer> [--dry|--log]"
    echo ""
    echo "Printers: $AVAILABLE_PRINTERS"
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

PRINTER="$1"
FLAG="${2:-}"

PRINTER_HOST=$(resolve_printer "$PRINTER" || true)
if [ -z "$PRINTER_HOST" ]; then
    echo "Unknown printer: $PRINTER"
    echo "Available: $AVAILABLE_PRINTERS"
    exit 1
fi

HOST="${SBC_USER}@${PRINTER_HOST}"

echo "==> Target: $HOST"

# --- Syntax check before deploying ---
echo "==> Checking Python syntax..."
errors=0
while IFS= read -r -d '' pyfile; do
    if ! python3 -m py_compile "$pyfile" 2>/dev/null; then
        echo "  SYNTAX ERROR: $pyfile"
        errors=$((errors + 1))
    fi
done < <(find "$SCRIPT_DIR/extras" -name '*.py' -print0)

if [ "$errors" -gt 0 ]; then
    echo "==> $errors syntax error(s) found. Aborting deploy."
    exit 1
fi
echo "  All files OK"

# --- Build rsync args ---
RSYNC_ARGS=(-avz --delete --exclude='__pycache__' --exclude='*.pyc')

if [ "$FLAG" = "--dry" ]; then
    RSYNC_ARGS+=(--dry-run)
    echo "==> DRY RUN (no changes will be made)"
fi

# --- Sync plugin files ---
echo "==> Syncing extras/ -> $REMOTE_ACE_DIR/"
rsync "${RSYNC_ARGS[@]}" \
    "$SCRIPT_DIR/extras/" \
    "$HOST:$REMOTE_ACE_DIR/"

# --- Sync moonraker component if it exists ---
if [ -f "$SCRIPT_DIR/moonraker/ace_manager.py" ]; then
    echo "==> Syncing moonraker component..."
    rsync "${RSYNC_ARGS[@]}" \
        "$SCRIPT_DIR/moonraker/ace_manager.py" \
        "$HOST:$REMOTE_MOONRAKER_COMPONENT"
fi

if [ "$FLAG" = "--dry" ]; then
    echo "==> Dry run complete."
    exit 0
fi

# --- Restart Klipper ---
echo "==> Restarting Klipper on $PRINTER..."
ssh "$HOST" "sudo systemctl restart klipper"
echo "  Klipper restarted"

# --- Optionally tail the log ---
if [ "$FLAG" = "--log" ]; then
    echo "==> Tailing klippy.log (Ctrl+C to stop)..."
    echo "---"
    ssh "$HOST" "tail -f ~/printer_data/logs/klippy.log"
fi

echo "==> Done."
