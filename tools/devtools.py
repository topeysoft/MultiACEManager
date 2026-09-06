"""JSON helpers for dev.sh (kept out of bash so quoting stays sane)."""
import json
import sys
import urllib.parse


def _load():
    return json.load(sys.stdin)


def state():
    """Read /server/info (fast) and print klippy state plus a one-line message."""
    try:
        r = _load()["result"]
        st = r.get("klippy_state") or ("disconnected" if not r.get("klippy_connected") else "unknown")
        print(st)
        print("" if st == "ready" else "see: ./dev.sh log 40 'Error|Traceback|shutdown'")
    except Exception:
        print("unreachable")
        print("")


def status():
    d = _load()["result"]["status"].get("ace")
    if d is None:
        print("no [ace] object loaded")
        sys.exit(1)
    print(f"devices={d['num_devices']} gates={d['total_gates']} "
          f"selected_gate={d.get('selected_gate')} endless_spool={d.get('endless_spool')}")
    for dev in d["devices"]:
        st = dev.get("status", {})
        slots = " ".join(
            f"{s['index']}:{s['status']}" + (f"/{s['type']}" if s.get("type") else "")
            for s in st.get("slots", []))
        print(f"  {dev['name']} {dev.get('connection_status')} gates={dev['gates']} "
              f"temp={st.get('temp')} dryer={st.get('dryer_status', {}).get('status')} status={st.get('status')}")
        print(f"     slots: {slots}")
        print(f"     port:  {dev['port']}")


def gcode_result():
    d = _load()
    if "error" in d:
        print("    ERROR:", d["error"].get("message"))
        sys.exit(1)


def responses(since):
    start = float(since) - 1
    for e in _load()["result"]["gcode_store"]:
        if e["time"] >= start and e["type"] == "response":
            print("    " + e["message"].replace("\n", "\n    "))


def quote(text):
    print(urllib.parse.quote(text))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"state": state, "status": status, "gcode_result": gcode_result,
     "responses": responses, "quote": quote}[cmd](*args)
