#!/usr/bin/env python3
"""Perseus fork: MANDATORY Arkham cross-check for every Desk 01 run (rule 2026-10-21).

  python helpers/arkham_xcheck.py RUN_DIR [--top 10] [--limit 100] [--fanouts 4] [--plan-only]

Live by default. Plan-only (no Arkham calls) with --plan-only, HF_DRY_RUN=1, or
HF_API_MODE in {count, emulate_zero_balance}. 0 Surf credits either way.
Key: ARKHAM_API_KEY from env only; never printed or written (errors scrubbed).

Writes RUN_DIR/.work/arkham_xcheck.json with evidence kept separate:
  labels      [A] Arkham entity / label per address
  facts       [F] transfer counts, contract flag, largest outflows (from Arkham transfers)
  inferences  [I] hub / treasury-like / exchange-flow hints — never presented as fact
  status      ok | partial (some calls errored) | failed | plan_only
Every transfer pull that returns the 100-row page cap (or count > returned) is
flagged truncated_at_cap: totals from it are lower bounds.
Also writes RUN_DIR/.work/fanout/<SYM>-fan-N-<role>.json specs accepted by
/workspace/style-refs/fanout.py (render: fanout.py spec.json out.png).
"""
from __future__ import annotations
import argparse, json, os, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = os.environ.get("ARKHAM_BASE_URL", "https://api.arkm.com").rstrip("/")
DHAKA = timezone(timedelta(hours=6))
CAP = 100
CG2ARK = {"binance-smart-chain": "bsc", "ethereum": "ethereum", "base": "base", "arbitrum-one": "arbitrum_one",
          "polygon-pos": "polygon", "optimistic-ethereum": "optimism", "avalanche": "avalanche"}
EXCH_WORDS = ("binance", "okx", "bybit", "bitget", "upbit", "coinbase", "kraken", "gate", "kucoin", "mexc", "htx", "bithumb")


def plan_only_forced() -> str | None:
    if os.environ.get("HF_DRY_RUN", "").lower() in ("1", "true", "yes"):
        return "HF_DRY_RUN"
    m = os.environ.get("HF_API_MODE", "live")
    return f"HF_API_MODE={m}" if m in ("count", "emulate_zero_balance") else None


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


def short(a: str) -> str:
    return a[:6] + "…" + a[-4:] if isinstance(a, str) and len(a) > 14 else str(a)


def _side(t: dict, side: str) -> tuple[str, str | None]:
    p = t.get(f"{side}Address") or {}
    if isinstance(p, str):
        return p.lower(), None
    ent = (p.get("arkhamEntity") or {}).get("name") or (p.get("arkhamLabel") or {}).get("name")
    return (p.get("address") or "").lower(), ent


def _amt(t):
    for k in ("unitValue", "value", "amount"):
        if t.get(k) is not None:
            try:
                return float(t[k])
            except (TypeError, ValueError):
                pass
    return 0.0


def _ts(t):
    v = t.get("blockTimestamp") or t.get("timestamp")
    try:
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v / (1000 if v > 1e12 else 1), timezone.utc)
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def plan(sk: dict, top: int):
    meta = sk.get("meta", {})
    plats = meta.get("coingecko_platforms") or {"binance-smart-chain": meta.get("contract_address")}
    out = []
    for cg, ca in plats.items():
        ch = CG2ARK.get(cg)
        tops = ((((meta.get("chain_lp_realtime") or {}).get(cg) or {}).get("top_holders_classified") or {})
                .get("unclassified") or {}).get("top") or []
        for h in tops[:top]:
            out.append({"chain": ch, "token": ca, "addr": h["addr"].lower(), "skeleton_balance": h.get("balance")})
    return out


def _safe_notes(run_dir: Path) -> dict:
    try:
        rv = json.loads((run_dir / ".work" / "rpc_verify.json").read_text())
        return {c["note"].split(" · ")[0].lower(): c["note"].split(" · ", 1)[1]
                for c in rv["checks"] if c["check"] == "holder_balance" and " · " in c["note"]}
    except Exception:
        return {}


def run(run_dir: Path, top=10, limit=CAP, plan_only=False, getter=None, n_fanouts=4) -> dict:
    getter = getter or _get
    sk = json.loads((run_dir / ".work" / "skeleton.json").read_text())
    sym = (sk.get("meta") or {}).get("symbol") or "TOKEN"
    forced = plan_only_forced()
    plan_only = plan_only or bool(forced)
    rpc_notes = _safe_notes(run_dir)
    labels, facts, infs, rows, errors, calls, fan_src = [], [], [], [], [], 0, []
    for p in plan(sk, top):
        r = dict(p)
        rows.append(r)
        if plan_only:
            continue
        a = p["addr"]
        intel = getter(f"/intelligence/address/{a}", {"chain": p["chain"]}); calls += 1
        if not isinstance(intel, dict) or "error" in intel:
            why = intel.get("error") if isinstance(intel, dict) else "bad response"
            r["intel_error"] = why; errors.append({"addr": a, "call": "intel", "reason": why})
            labels.append({"addr": a, "chain": p["chain"], "entity": "UNKNOWN", "label": None, "reason": why, "tag": "A"})
        else:
            ent = (intel.get("arkhamEntity") or {}).get("name")
            lab = (intel.get("arkhamLabel") or {}).get("name")
            r.update(entity=ent, label=lab, is_contract=intel.get("contract"))
            labels.append({"addr": a, "chain": p["chain"], "entity": ent or "unlabelled", "label": lab, "tag": "A"})
        tr = getter("/transfers", {"base": a, "tokens": p["token"], "chains": p["chain"], "flow": "out",
                                   "limit": min(limit, CAP), "sortKey": "time", "sortDir": "desc"}); calls += 1
        if not isinstance(tr, dict) or "error" in tr:
            why = tr.get("error") if isinstance(tr, dict) else "bad response"
            r["transfers_error"] = why; errors.append({"addr": a, "call": "transfers", "reason": why})
            facts.append({"addr": a, "fact": "UNKNOWN", "reason": why, "tag": "F"}); continue
        r.update(truncation(tr, limit))
        outs = []
        for t in tr.get("transfers") or []:
            fr, _ = _side(t, "from"); to, to_ent = _side(t, "to")
            if fr == a and to:
                outs.append({"to": to, "to_entity": to_ent, "amount": _amt(t), "ts": _ts(t),
                             "tx": (t.get("transactionHash") or "")[:18]})
        dests = {o["to"] for o in outs}
        tot = sum(o["amount"] for o in outs)
        facts.append({"addr": a, "tag": "F", "outflow_transfers": len(outs), "distinct_destinations": len(dests),
                      "outflow_total": round(tot, 4), "truncated_at_cap": r["truncated_at_cap"],
                      "lower_bound": r["truncated_at_cap"], "is_contract": r.get("is_contract"),
                      "rpc_note": rpc_notes.get(a)})
        ex = [o for o in outs if o["to_entity"] and any(w in o["to_entity"].lower() for w in EXCH_WORDS)]
        if len(dests) >= 5:
            infs.append({"addr": a, "tag": "I", "inference": f"distribution hub: {len(dests)} distinct recipients"})
        if (rpc_notes.get(a) or "").startswith("Safe") and not outs:
            infs.append({"addr": a, "tag": "I", "inference": "treasury-like Safe: no outflows in window"})
        if ex:
            infs.append({"addr": a, "tag": "I", "inference": f"exchange-bound flow: {len(ex)} transfers to "
                         + ", ".join(sorted({o['to_entity'] for o in ex}))})
        if outs:
            fan_src.append((a, r, outs, tot))
    # fan-out specs (style-refs/fanout.py)
    fan_dir = run_dir / ".work" / "fanout"
    fan_files = []
    for i, (a, r, outs, tot) in enumerate(sorted(fan_src, key=lambda x: -x[3])[:n_fanouts], 1):
        agg = {}
        for o in outs:
            g = agg.setdefault(o["to"], {"amount": 0.0, "ts": o["ts"], "ent": o["to_entity"], "tx": o["tx"]})
            g["amount"] += o["amount"]
            if o["ts"] and (g["ts"] is None or o["ts"] < g["ts"]):
                g["ts"] = o["ts"]
        tg = sorted(agg.items(), key=lambda kv: -kv[1]["amount"])[:6]
        first = min((g["ts"] for _, g in tg if g["ts"]), default=None)
        role = "Hub" if len(agg) >= 5 else "Source"
        spec = {"headline": {"date": first.strftime("%Y-%m-%d") if first else "—",
                             "time": first.strftime("%H:%M") if first else "—"},
                "title": f"${sym} {short(a)}: top outflows ({'lower bound, 100-cap' if r.get('truncated_at_cap') else 'complete window'})",
                "source": {"role": role, "addr": short(a), "arkham_label": r.get("entity") or r.get("label") or "unlabelled",
                           "sub": f"{len(outs)} outflows · {len(agg)} recipients [F]"},
                "targets": [{"addr": short(k), "amount": f"{g['amount']:,.0f}",
                             "ts_utc": g["ts"].strftime("%Y-%m-%d %H:%M UTC") if g["ts"] else "—",
                             "note": f"[A] {g['ent']}" if g["ent"] else "[A] unlabelled",
                             "link": "F", "tx": g["tx"]} for k, g in tg],
                "total": f"{sum(g['amount'] for _, g in tg):,.0f}", "ticker": f"${sym}",
                "total_caption": "Top recipients shown [F]" + (" · truncated at 100 transfers" if r.get("truncated_at_cap") else ""),
                "source_line": "Source: Arkham transfers API [F], labels [A]"}
        fan_dir.mkdir(parents=True, exist_ok=True)
        f = fan_dir / f"{sym}-fan-{i}-{role.lower()}-{a[2:6]}.json"
        f.write_text(json.dumps(spec, indent=1, ensure_ascii=False)); fan_files.append(str(f))
    n = len(rows)
    if plan_only:
        status = "plan_only"
    elif n == 0:
        status = "failed"; errors.append({"addr": None, "call": "plan", "reason": "no holders in skeleton"})
    elif len(errors) >= 2 * n:
        status = "failed"
    else:
        status = "partial" if errors else "ok"
    doc = {"written": datetime.now(DHAKA).strftime("%Y-%m-%d %H:%M:%S+06"), "symbol": sym,
           "mode": "plan_only" if plan_only else "live", "plan_only_reason": forced or ("--plan-only" if plan_only else None),
           "status": status, "arkham_calls": calls, "surf_credits": 0, "page_cap": CAP,
           "truncated": [r["addr"] for r in rows if r.get("truncated_at_cap")],
           "labels": labels, "facts": facts, "inferences": infs, "errors": errors,
           "fanout_specs": fan_files, "rows": rows}
    (run_dir / ".work" / "arkham_xcheck.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False, default=str))
    return doc


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir")
    ap.add_argument("--top", type=int, default=10); ap.add_argument("--limit", type=int, default=CAP)
    ap.add_argument("--fanouts", type=int, default=4); ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    d = run(Path(a.run_dir), a.top, a.limit, a.plan_only, n_fanouts=a.fanouts)
    print(f"ARKHAM {d['status'].upper()} ({d['mode']}): {len(d['rows'])} addresses, {d['arkham_calls']} calls, "
          f"{len(d['errors'])} errors, {len(d['truncated'])} truncated at {CAP}, {len(d['fanout_specs'])} fan-out specs")
    raise SystemExit(0 if d["status"] in ("ok", "partial", "plan_only") else 1)
