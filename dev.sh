#!/bin/bash
#
# KlipperACE development loop. One command per step, plain-text output.
#
#   ./dev.sh check                    syntax-compile every plugin file
#   ./dev.sh test [pytest args]       run the offline test suite (simulator, no printer)
#   ./dev.sh deploy [--dry|--no-restart]
#                                     move the printer's ~/KlipperACE clone to HEAD (must be committed
#                                     and pushed), restart Klipper, wait, show ACE status
#   ./dev.sh deploy --wip             rsync the working tree into that clone instead (shows as dirty)
#   ./dev.sh versions                 KlipperACE on every ACE printer vs origin; non-zero on drift
#   ./dev.sh loop                     check + test + deploy (--wip when uncommitted; the standard iteration)
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
REMOTE_REPO="~/KlipperACE"
ACE_PRINTERS="${ACE_PRINTERS:-obi1 r2d2}"

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

# The printer's ~/KlipperACE clone is the install: Klipper's extras/ace and Moonraker's
# ace_manager.py are symlinks into it, and Moonraker's update manager tracks it. So what the
# Software Updates panel shows is what runs, and nothing can sit on an old copy unnoticed.
# Runs on the printer: make the links (moving an old per-file install aside) and point the
# update manager at the branch being deployed. Prints MOONRAKER_CHANGED when Moonraker
# must restart to pick something up.
remote_ensure_install() {
    local branch="$1"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s -- "$branch" <<'EOF'
set -e
branch="$1"; repo="$HOME/KlipperACE"
[ -d "$repo/.git" ] || git clone -q -b "$branch" https://github.com/topeysoft/MultiACEManager "$repo"
ace="$HOME/klipper/klippy/extras/ace"
if [ "$(readlink "$ace" || true)" != "$repo/extras" ]; then
    if [ -e "$ace" ] && [ ! -L "$ace" ]; then
        backup="$HOME/ace-install-backup-$(date +%Y%m%d-%H%M%S)"
        mv "$ace" "$backup"; echo "    old install moved to $backup"
    fi
    ln -sfn "$repo/extras" "$ace"; echo "    linked $ace -> $repo/extras"
fi
comp="$HOME/moonraker/moonraker/components/ace_manager.py"
if [ -d "$(dirname "$comp")" ] && [ "$(readlink "$comp" || true)" != "$repo/moonraker/ace_manager.py" ]; then
    ln -sfn "$repo/moonraker/ace_manager.py" "$comp"; echo "    linked $comp"; echo MOONRAKER_CHANGED
fi
conf="$HOME/printer_data/config/moonraker.conf"
if [ -f "$conf" ] && grep -q '^\[update_manager KlipperACE\]' "$conf"; then
    current="$(sed -n '/^\[update_manager KlipperACE\]/,/^\[/s/^primary_branch:[[:space:]]*//p' "$conf")"
    if [ "$current" != "$branch" ]; then
        sed -i "/^\[update_manager KlipperACE\]/,/^\[/s/^primary_branch:.*/primary_branch: $branch/" "$conf"
        echo "    update manager now tracks $branch (was ${current:-unset})"; echo MOONRAKER_CHANGED
    fi
fi
EOF
}

cmd_deploy() {
    local dry=0 restart=1 wip=0
    for a in "$@"; do case "$a" in --dry) dry=1 ;; --no-restart) restart=0 ;; --wip) wip=1 ;; esac; done
    cmd_check
    local branch sha
    branch="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"
    sha="$(git -C "$SCRIPT_DIR" rev-parse HEAD)"
    if [ "$wip" -eq 0 ]; then
        if [ -n "$(git -C "$SCRIPT_DIR" status --porcelain -- extras moonraker)" ]; then
            echo "==> Uncommitted changes in extras/ or moonraker/. Commit and push, or use --wip for a throwaway test."
            return 1
        fi
        git -C "$SCRIPT_DIR" fetch -q origin "$branch"
        if ! git -C "$SCRIPT_DIR" merge-base --is-ancestor HEAD "origin/$branch"; then
            echo "==> HEAD ${sha:0:7} is not on origin/$branch. Push first, so the printer can fetch it."
            return 1
        fi
    fi
    if [ "$dry" -eq 1 ]; then
        echo "==> Dry run: $PRINTER would get $([ "$wip" -eq 1 ] && echo "the working tree (wip)" || echo "$branch @ ${sha:0:7}")"
        cmd_versions || true
        return 0
    fi

    echo "==> Checking the install layout on $PRINTER"
    local out moonraker=0
    out="$(remote_ensure_install "$branch")"
    [ -n "$out" ] && echo "$out" | grep -v '^MOONRAKER_CHANGED$' || true
    echo "$out" | grep -q '^MOONRAKER_CHANGED$' && moonraker=1

    if [ "$wip" -eq 1 ]; then
        local rsync_args=(-rlptz --delete --exclude='__pycache__' --exclude='*.pyc' -e "ssh ${SSH_OPTS[*]}" -i)
        echo "==> rsync working tree -> $SSH_TARGET:$REMOTE_REPO (wip: the clone shows as dirty until the next deploy)"
        out="$(rsync "${rsync_args[@]}" "$SCRIPT_DIR/extras/" "$SSH_TARGET:$REMOTE_REPO/extras/")"
        echo "$out" | grep -E '^[<>ch*]' | sed 's/^/    /' || true
        out="$(rsync "${rsync_args[@]}" "$SCRIPT_DIR/moonraker/ace_manager.py" "$SSH_TARGET:$REMOTE_REPO/moonraker/ace_manager.py")"
        if echo "$out" | grep -qE '^[<>ch*]'; then echo "    moonraker/ace_manager.py"; moonraker=1; fi
    else
        echo "==> $PRINTER: $REMOTE_REPO -> $branch @ ${sha:0:7}"
        out="$(ssh "${SSH_OPTS[@]}" "$SSH_TARGET" bash -s -- "$branch" "$sha" <<'EOF'
set -e
cd "$HOME/KlipperACE"
before="$(md5sum moonraker/ace_manager.py 2>/dev/null || true)"
old="$(git rev-parse --short HEAD)"
git fetch -q origin "$1"
git reset -q --hard
git clean -qfd -- extras moonraker
git checkout -q -B "$1" "$2"
git branch -q --set-upstream-to="origin/$1"
echo "    was $old"
[ "$before" = "$(md5sum moonraker/ace_manager.py 2>/dev/null || true)" ] || echo MOONRAKER_CHANGED
EOF
)"
        echo "$out" | grep -v '^MOONRAKER_CHANGED$' || true
        echo "$out" | grep -q '^MOONRAKER_CHANGED$' && moonraker=1
    fi

    if [ "$restart" -eq 0 ]; then
        echo "==> Deployed (no restart)$([ "$moonraker" -eq 1 ] && echo "; Moonraker needs a restart too")"
    else
        [ "$moonraker" -eq 1 ] && cmd_restart moonraker
        cmd_restart klipper && { sleep 6; cmd_status; }
    fi
    cmd_versions || true
}

# KlipperACE on every ACE printer, compared with origin. Exit status 1 when any printer is
# behind, dirty, unreachable or not on the linked install, so it can gate other scripts.
cmd_versions() {
    local branch drift=0 p host line sha dirty linked count
    branch="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"
    git -C "$SCRIPT_DIR" fetch -q origin "$branch" || echo "    (could not fetch origin; comparing with the last fetch)"
    echo "==> KlipperACE: origin/$branch is $(git -C "$SCRIPT_DIR" rev-parse --short "origin/$branch")"
    for p in $ACE_PRINTERS; do
        host="$(resolve_printer "$p")"
        line="$(ssh "${SSH_OPTS[@]}" "${SBC_USER}@${host}" '
            cd ~/KlipperACE 2>/dev/null || { echo "none - - -"; exit 0; }
            dirty=$(git status --porcelain -- extras moonraker | wc -l)
            [ "$(readlink ~/klipper/klippy/extras/ace)" = "$HOME/KlipperACE/extras" ] && linked=yes || linked=no
            echo "$(git rev-parse HEAD) $(git rev-parse --abbrev-ref HEAD) $dirty $linked"' 2>/dev/null)" \
            || { printf '    %-5s unreachable\n' "$p"; drift=1; continue; }
        read -r sha pbranch dirty linked <<<"$line"
        if [ "$sha" = "none" ]; then printf '    %-5s no ~/KlipperACE clone\n' "$p"; drift=1; continue; fi
        local notes=()
        if ! git -C "$SCRIPT_DIR" cat-file -e "$sha^{commit}" 2>/dev/null; then
            notes+=("commit unknown here"); drift=1
        else
            count="$(git -C "$SCRIPT_DIR" rev-list --count "$sha..origin/$branch")"
            [ "$count" -gt 0 ] && { notes+=("$count behind"); drift=1; }
            count="$(git -C "$SCRIPT_DIR" rev-list --count "origin/$branch..$sha")"
            [ "$count" -gt 0 ] && { notes+=("$count not on origin"); drift=1; }
        fi
        [ "$pbranch" != "$branch" ] && { notes+=("on branch $pbranch"); drift=1; }
        [ "$dirty" -gt 0 ] && { notes+=("wip: $dirty changed file(s)"); drift=1; }
        [ "$linked" != "yes" ] && { notes+=("old per-file install"); drift=1; }
        [ ${#notes[@]} -eq 0 ] && notes=("up to date")
        printf '    %-5s %s  %s\n' "$p" "${sha:0:7}" "$(IFS=,; echo "${notes[*]}" | sed 's/,/, /g')"
    done
    [ "$drift" -eq 0 ] || echo "    fix: ./dev.sh --printer <name> deploy"
    return "$drift"
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

cmd_loop() {
    local mode=""
    [ -n "$(git -C "$SCRIPT_DIR" status --porcelain -- extras moonraker)" ] && mode="--wip"
    cmd_check && cmd_test -q && cmd_deploy $mode
}

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
    versions) cmd_versions ;;
    log) cmd_log "$@" ;;
    ace-log) cmd_ace_log ;;
    ssh) cmd_ssh "$@" ;;
    sim) cmd_sim "$@" ;;
    printers) echo "obi1 (main ACE test printer), r2d2, c3po" ;;
    *) sed -n '3,22p' "$0" ;;
esac
