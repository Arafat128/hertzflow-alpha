#!/usr/bin/env python3
"""Perseus fork: 0-credit Surf key health check. NEVER prints key values.

Surf (CLI 1.0.9 / docs checked 2026-10-26) has no 0-credit balance or whoami
endpoint, so this does NOT call Surf at all. It reports, per SURF_API_KEY_4..11:
  set / not set, and the ledger state learned reactively by the pipeline
  (PAID_BALANCE_ZERO seen at <time UTC+06>, still within TTL or expired).
Exit code: 0 = at least one key not known-empty, 3 = every set key known-empty,
4 = no pool keys set.
  --reset NAME|all   forget ledger entries (after a top-up on the same key)
  --json             machine-readable
"""
import argparse, json, os, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import api_gateway as gw

DHAKA = timezone(timedelta(hours=6))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    led = gw.load_ledger()
    if a.reset:
        names = list(led) if a.reset == "all" else [a.reset]
        for n in names:
            led.pop(n, None)
        gw.save_ledger(led)
        print(f"ledger: reset {', '.join(names) or 'nothing'}")
    rows, alive, n_set = [], 0, 0
    for i in range(4, 12):
        n = f"SURF_API_KEY_{i}"
        v = os.environ.get(n, "")
        e = led.get(n)
        if not v:
            st = "not set"
        else:
            n_set += 1
            if gw.ledger_dead(n, v, led):
                st = "known-empty (PAID_BALANCE_ZERO)"
            else:
                st = "ok (not known-empty)"
                alive += 1
        seen = (datetime.fromtimestamp(e["ts"], DHAKA).strftime("%Y-%m-%d %H:%M+06")
                if e and v and e.get("fp") == gw._key_fp(v) else None)
        rows.append({"key": n, "status": st, "pbz_seen": seen})
    out = {"ledger": str(gw._ledger_path()), "ttl_h": gw._env_int("HF_KEY_LEDGER_TTL_H", 24),
           "keys": rows, "alive": alive, "set": n_set,
           "probe": "none — Surf has no 0-credit balance endpoint; rotation stays reactive"}
    if a.json:
        print(json.dumps(out, indent=1))
    else:
        for r in rows:
            print(f"{r['key']:<16} {r['status']:<34} {('PBZ ' + r['pbz_seen']) if r['pbz_seen'] else ''}")
        print(f"alive {alive}/{n_set} · ledger {out['ledger']} · {out['probe']}")
    if n_set == 0:
        return 4
    return 0 if alive else 3


if __name__ == "__main__":
    sys.exit(main())
