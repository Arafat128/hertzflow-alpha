#!/usr/bin/env python3
"""Perseus fork: Arkham cross-check of a finished run (no Surf credits).

  python helpers/arkham_xcheck.py RUN_DIR [--top 10] [--limit 100] [--live]

Key: ARKHAM_API_KEY from the environment only; never printed or written
(error bodies are scrubbed). Without --live it is a plan-only dry run: lists the
calls it would make and makes none (Arkham quota is untouched).
For each top holder from the skeleton (per chain) it fetches address intel and
the last `limit` token transfers. A transfer list that comes back with
returned == limit (Arkham page cap 100 for these pulls) or count > returned is
flagged `truncated_at_cap` — totals built from it are lower bounds.
Writes RUN_DIR/.work/arkham_xcheck.json.
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.environ.get("ARKHAM_BASE_URL", "https://api.arkm.com").rstrip("/")
DHAKA = timezone(timedelta(hours=6))
CAP = 100
CG2ARK = {"binance-smart-chain": "bsc", "ethereum": "ethereum", "base": "base", "arbitrum-one": "arbitrum_one",
          "polygon-pos": "polygon", "optimistic-ethereum": "optimism", "avalanche": "avalanche"}


def _scrub(t: str, key: str) -> str:
    return t.replace(key, "<redacted>") if key else t


def _get(path: str, params: dict | None = None):
    key = os.environ.get("ARKHAM_API_KEY", "").strip()
    if not key:
        return {"error": "ARKHAM_API_KEY not set"}
    q = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
    req = urllib.request.Request(f"{BASE}{path}{'?' + q if q else ''}",
                                 headers={"API-Key": key, "Accept": "application/json", "User-Agent": "hertzflow-perseus"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(2 ** attempt); continue
            return {"error": f"HTTP {e.code}", "body": _scrub(e.read().decode("utf-8", "replace"), key)[:300]}
        except Exception as e:
            return {"error": _scrub(f"{type(e).__name__}: {e}", key)}
    return {"error": "429 retries exhausted"}


def truncation(resp: dict, limit: int) -> dict:
    rows = resp.get("transfers") or []
    cnt = resp.get("count")
    trunc = len(rows) >= min(limit, CAP) or (isinstance(cnt, int) and cnt > len(rows))
    return {"returned": len(rows), "count": cnt, "truncated_at_cap": bool(trunc)}


def plan(sk: dict, top: int):
    meta = sk.get("meta", {})
    out = []
    for cg, ca in (meta.get("coingecko_platforms") or {}).items():
        ch = CG2ARK.get(cg)
        tops = ((((meta.get("chain_lp_realtime") or {}).get(cg) or {}).get("top_holders_classified") or {})
                .get("unclassified") or {}).get("top") or []
        for h in tops[:top]:
            out.append({"chain": ch, "token": ca, "addr": h["addr"], "skeleton_balance": h.get("balance")})
    return out


def run(run_dir: Path, top=10, limit=CAP, live=False, getter=None) -> dict:
    getter = getter or _get
    sk = json.loads((run_dir / ".work" / "skeleton.json").read_text())
    rows, calls = [], 0
    for p in plan(sk, top):
        r = dict(p)
        if live:
            intel = getter(f"/intelligence/address/{p['addr']}", {"chain": p["chain"]}); calls += 1
            ent = (intel.get("arkhamEntity") or {}) if isinstance(intel, dict) else {}
            lab = (intel.get("arkhamLabel") or {}) if isinstance(intel, dict) else {}
            r["entity"] = ent.get("name"); r["label"] = lab.get("name")
            r["is_contract"] = intel.get("contract") if isinstance(intel, dict) else None
            tr = getter("/transfers", {"base": p["addr"], "tokens": p["token"], "chains": p["chain"],
                                       "limit": min(limit, CAP), "sortKey": "time", "sortDir": "desc"}); calls += 1
            if isinstance(tr, dict) and "error" not in tr:
                r.update(truncation(tr, limit))
            else:
                r["error"] = (tr or {}).get("error") if isinstance(tr, dict) else "bad response"
        rows.append(r)
    doc = {"written": datetime.now(DHAKA).strftime("%Y-%m-%d %H:%M:%S+06"), "mode": "live" if live else "plan_only",
           "arkham_calls": calls, "surf_credits": 0, "page_cap": CAP,
           "truncated": [r["addr"] for r in rows if r.get("truncated_at_cap")], "rows": rows}
    (run_dir / ".work" / "arkham_xcheck.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir")
    ap.add_argument("--top", type=int, default=10); ap.add_argument("--limit", type=int, default=CAP)
    ap.add_argument("--live", action="store_true")
    a = ap.parse_args()
    d = run(Path(a.run_dir), a.top, a.limit, a.live)
    print(f"{d['mode']}: {len(d['rows'])} addresses, {d['arkham_calls']} Arkham calls, "
          f"{len(d['truncated'])} truncated at {CAP} → {Path(a.run_dir) / '.work' / 'arkham_xcheck.json'}")
