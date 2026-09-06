#!/bin/bash
#
# KlipperACE development loop. One command per step, plain-text output.
#
#   ./dev.sh check                    syntax-compile every plugin file
#   ./dev.sh test [pytest args]       run the offline test suite (simulator, no printer)
#   ./dev.sh deploy [--dry|--no-restart]
#                                     rsync extras/ + moonraker component, restart Klipper, wait, show ACE status
#   ./dev.sh loop                     check + test + deploy   (the standard iteration)
#   ./dev.sh restart [klipper|moonraker|firmware]
#   ./dev.sh wait [seconds]           block until Klipper is ready (or prints the error)
#   ./dev.sh gcode "ACE_GET_STATUS"   run a G-code command and print its console replies
#   ./dev.sh status                   ACE object summary (devices, gates, slots)
#   ./dev.sh log [N] [pattern]        last N lines of klippy.log, optionally filtered
#   ./dev.sh ace-log                  ACE lines since the last Klipper start
#   ./dev.sh ssh [cmd]                shell on the printer
#   ./dev.sh sim [-n 2]               start the pty ACE simulator locally
#
# Target printer: ACE_PRINTER env var or --printer NAME (default: obi1).
# Restarts and log reads go over Moonraker HTTP; file sync uses rsync over SSH.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SBC_USER="${SBC_USER:-pi}"
PRINTER="${ACE_PRINTER:-obi1}"
VENV="${ACE_VENV:-$HOME/.venvs/klipperace}"
REMOTE_ACE_DIR="~/klipper/klippy/extras/ace"
REMOTE_MOONRAKER_COMPONENT="~/moonraker/moonraker/components/ace_manager.py"

resolve_printer() {
    case "$1" in
        obi1) echo "obi1.local" ;;
        r2d2) echo "r2d2.local" ;;
        c3po) echo "c3po.local" ;;
        *)    return 1 ;;
    esac
}

if [ "${1:-}" = "--printer" ]; then PRINTER="$2"; shift 2; fi
HOST="$(resolve_printer "$PRINTER" || true)"
[ -n "$HOST" ] || { echo "Unknown printer '$PRINTER' (obi1, r2d2, c3po)"; exit 1; }
SSH_TARGET="${SBC_USER}@${HOST}"
API="http://${HOST}:7125"
SSH_OPTS=(-4 -o BatchMode=yes -o ConnectTimeout=8 -o LogLevel=ERROR)

if [ -x "$VENV/bin/python" ]; then PY="$VENV/bin/python"; else PY="python3"; fi

api_get()  { curl -4 -s -m "${2:-15}" "$API$1"; }
api_post() { curl -4 -s -m "${2:-30}" -X POST "$API$1"; }

klippy_state() { api_get /server/info 15 | "$PY" "$SCRIPT_DIR/tools/devtools.py" state; }

cmd_check() {
    echo "==> Compiling extras/ with $PY"
    local errors=0
    while IFS= read -r -d '' f; do
        "$PY" -m py_compile "$f" 2>/dev/null || { echo "  SYNTAX ERROR: $f"; "$PY" -m py_compile "$f" || true; errors=$((errors+1)); }
    done < <(find "$SCRIPT_DIR/extras" "$SCRIPT_DIR/moonraker" -name '*.py' -print0)
    find "$SCRIPT_DIR/extras" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
    [ "$errors" -eq 0 ] && echo "  OK" || { echo "  $errors error(s)"; return 1; }
}

cmd_test() {
    [ -x "$VENV/bin/pytest" ] || { echo "No venv at $VENV. Create: python3 -m venv $VENV && $VENV/bin/pip install pyserial pytest requests"; return 1; }
    cd "$SCRIPT_DIR" && "$VENV/bin/pytest" "$@"
}

cmd_wait() {
    local timeout="${1:-90}" waited=0 state msg
    while [ "$waited" -lt "$timeout" ]; do
        { read -r state; read -r msg; } < <(klippy_state)
        case "$state" in
            ready) echo "==> Klipper ready (${waited}s)"; return 0 ;;
            error|shutdown) echo "==> Klipper $state after ${waited}s:"; echo "$msg" | sed 's/^/    /'; return 1 ;;
        esac
        sleep 3; waited=$((waited+3))
    done
    echo "==> Timed out after ${timeout}s (state: ${state:-unknown})"; return 1
}

cmd_restart() {
    local what="${1:-klipper}"
    case "$what" in
        firmware) echo "==> FIRMWARE_RESTART"; api_post "/printer/firmware_restart" >/dev/null ;;
        klipper|moonraker) echo "==> Restarting $what via Moonraker"; api_post "/machine/services/restart?service=$what" 20 >/dev/null ;;
        *) echo "restart: klipper|moonraker|firmware"; return 1 ;;
    esac
    sleep 3
    [ "$what" = "moonraker" ] || cmd_wait
}

cmd_deploy() {
    local dry=0 restart=1
    for a in "$@"; do case "$a" in --dry) dry=1 ;; --no-restart) restart=0 ;; esac; done
    cmd_check
    local rsync_args=(-rlptz --delete --exclude='__pycache__' --exclude='*.pyc' -e "ssh ${SSH_OPTS[*]}")
    [ "$dry" -eq 1 ] && rsync_args+=(--dry-run -v)
    echo "==> rsync extras/ -> $SSH_TARGET:$REMOTE_ACE_DIR"
    rsync "${rsync_args[@]}" -i "$SCRIPT_DIR/extras/" "$SSH_TARGET:$REMOTE_ACE_DIR/" | grep -E '^[<>ch*]' | sed 's/^/    /' || true
    if [ -f "$SCRIPT_DIR/moonraker/ace_manager.py" ]; then
        echo "==> rsync moonraker/ace_manager.py"
        rsync "${rsync_args[@]}" -i "$SCRIPT_DIR/moonraker/ace_manager.py" "$SSH_TARGET:$REMOTE_MOONRAKER_COMPONENT" | grep -E '^[<>ch*]' | sed 's/^/    /' || true
    fi
    [ "$dry" -eq 1 ] && { echo "==> Dry run done"; return 0; }
    [ "$restart" -eq 1 ] || { echo "==> Deployed (no restart)"; return 0; }
    cmd_restart klipper && { sleep 6; cmd_status; }
}

cmd_gcode() {
    [ $# -ge 1 ] || { echo "usage: gcode \"COMMAND ARGS\""; return 1; }
    local script="$*" start
    start="$(date +%s)"
    local encoded; encoded="$("$PY" "$SCRIPT_DIR/tools/devtools.py" quote "$script")"
    echo "==> $script"
    local result; result="$(curl -4 -s -m 600 -X POST "$API/printer/gcode/script?script=$encoded")"
    echo "$result" | "$PY" "$SCRIPT_DIR/tools/devtools.py" gcode_result || true
    sleep 0.5
    api_get "/server/gcode_store?count=200" | "$PY" "$SCRIPT_DIR/tools/devtools.py" responses "$start"
}

cmd_status() { api_get "/printer/objects/query?ace" | "$PY" "$SCRIPT_DIR/tools/devtools.py" status; }

cmd_log() {
    local n="${1:-60}" pattern="${2:-}"
    if [ -n "$pattern" ]; then api_get /server/files/klippy.log 60 | grep -iE "$pattern" | tail -n "$n"
    else api_get /server/files/klippy.log 60 | tail -n "$n"; fi
}

cmd_ace_log() {
    api_get /server/files/klippy.log 60 | awk '/^Start printer at/{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' \
        | grep -iE 'ace|Traceback|Error|Exception' | grep -vE '^\s|^\[gcode_macro|description =|^[a-z_]+ =|Args:|^Stats '
}

cmd_ssh() { ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"; }

cmd_sim() { cd "$SCRIPT_DIR" && "$PY" tests/ace_sim.py "$@"; }

cmd_loop() { cmd_check && cmd_test -q && cmd_deploy; }

cmd="${1:-help}"; shift || true
case "$cmd" in
    check) cmd_check ;;
    test) cmd_test "$@" ;;
    deploy) cmd_deploy "$@" ;;
    loop) cmd_loop ;;
    restart) cmd_restart "$@" ;;
    wait) cmd_wait "$@" ;;
    gcode) cmd_gcode "$@" ;;
    status) cmd_status ;;
    log) cmd_log "$@" ;;
    ace-log) cmd_ace_log ;;
    ssh) cmd_ssh "$@" ;;
    sim) cmd_sim "$@" ;;
    printers) echo "obi1 (main ACE test printer), r2d2, c3po" ;;
    *) sed -n '3,22p' "$0" ;;
esac
