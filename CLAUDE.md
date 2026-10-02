# KlipperACE — working notes for Claude

Klipper plugin (`extras/`) plus a Moonraker component (`moonraker/`) driving Anycubic ACE Pro
filament units. Installed on the printer as `~/klipper/klippy/extras/ace/` (package name `ace`).

## Dev loop (use these, not ad-hoc ssh/curl)

```
./dev.sh check              # py_compile everything
./dev.sh test               # offline suite: tests/ against the simulator, <1s
./dev.sh deploy             # rsync -> obi1, restart Klipper, wait, print ACE status
./dev.sh loop               # check + test + deploy
./dev.sh gcode "ACE_GET_STATUS"   # run G-code, print console replies
./dev.sh status             # devices / gates / slots from the ace object
./dev.sh ace-log            # ACE log lines since last Klipper start
./dev.sh log 80 "Traceback|Error"
./dev.sh restart klipper|moonraker|firmware
./dev.sh ssh 'cmd'
```

Default target is **obi1** (the main ACE test printer, 2 units, 8 gates). Override with
`ACE_PRINTER=r2d2` or `./dev.sh --printer r2d2 ...`. Moonraker HTTP needs no API key from the Mac;
SSH is key-based as `pi`, with passwordless `systemctl restart klipper|moonraker`.

Python for local work: `~/.venvs/klipperace` (pyserial, pytest, requests). Do not use the iCloud
`.venv` in the parent folder.

## Testing rules

- Read-only commands may be run on obi1 any time: `ACE_GET_STATUS`, `ACE_LIST_DEVICES`,
  `ACE_SCAN_DEVICES`, `ACE_SHOW_USB_INFO`, `ACE_GET_DRYER_STATUS`, `ACE_DEBUG` with `get_*` methods.
- Commands that move filament or heat (`ACE_FEED`, `ACE_RETRACT`, `ACE_CHANGE_TOOL`, `T0`..`T7`,
  `ACE_START_DRYING`, `ACE_ENABLE_FEED_ASSIST`) need the user's go-ahead for that specific run.
- Restarting Klipper on an idle printer is fine. Check `./dev.sh status` / print state first if unsure.
- Every driver/protocol change gets a test in `tests/` first; the simulator (`tests/ace_sim.py`)
  models the device, `tests/fake_reactor.py` replaces Klipper's reactor with a manual clock.
- `python tests/ace_sim.py -n 2` exposes simulated units as ptys for `serial_ports:` in `[ace]`.

## Layout

- `extras/protocol/` framing + CRC (pure Python) · `extras/device/` serial driver, discovery,
  multi-device manager · `extras/commands/` G-code handlers · `extras/ace_controller.py` glue.
- Klipper entry points: `load_config` / `load_config_prefix` in `extras/__init__.py`.
- Repo `ace.cfg` uses `serial_ports:`; obi1's live `ace.cfg` uses `auto_detect: true` and
  `log_level: DEBUG`. The printer's copy of the config lives in the parent repo under `OBI1/`.

- Every G-code handler is registered through `gcode_guard` (extras/exceptions.py) so an
  `AceException` becomes `gcmd.error`; a test enforces this for all command modules.

- Unload sensor clearing is synchronized (ACE leads, extruder follows at the same speed); see
  `_sequential_retract_to_clear_sensor` and tests/test_unload_sync.py. Do not make it sequential again.

## Gotchas

- This checkout lives in iCloud Drive. Evicted files hang on read; `brctl download <path>` fetches
  them. `ls -lO` shows `dataless` for evicted files.
- obi1 also has a stale clone at `~/KlipperACE` (Moonraker update-manager entry, branch
  `multi-ace-dev`). The installed code is what `dev.sh deploy` rsyncs, not that clone.
- ACE units enumerate under `/dev/serial/by-path/`; the `usbv2` symlink can lag at boot, the
  driver retries. Both by-id links collide (`usb-ANYCUBIC_ACE_1`), so by-path is required.
- Packet framing parses header + length (`find_packet_in_buffer`), never the tail byte. A 0xFE
  in the CRC or length used to truncate packets ("Incomplete packet" + 2s timeouts); fixed 2026-09-05,
  regression tests in `tests/test_packet.py`.
- At boot ACE_1's `usbv2` by-path link can be missing for a moment: one "could not open port" retry
  and sometimes one EIO write error, then it reconnects. Harmless unless it repeats.
