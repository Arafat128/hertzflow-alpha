#!/usr/bin/env python3
"""Perseus fork: short Surf web-chat checklist, fed by .work/rpc_verify.json.

Anything RPC already proved (MATCH) is listed in one line and NOT sent to Surf.
Surf gets only: RPC MISMATCH / DRIFT / UNVERIFIED items, skeleton data gaps,
and the off-chain claims RPC cannot see (unlocks, labels, interpretation).
  surf_checklist.py RUN_DIR [--extra "claim" ...]  → RUN_DIR/surf-verify-checklist.auto.md
"""
import argparse, json, sys
from pathlib import Path

OFFCHAIN = ["Unlock / vesting dates and amounts (next two events).",
            "Entity labels for the top non-Safe holders and exchange wallets.",
            "Interpretation: who controls the largest holders (team / treasury / MM)?"]


def short(a):
    return a[:6] + "…" + a[-4:] if isinstance(a, str) and a.startswith("0x") and len(a) > 14 else a


def build(run: Path, extra=()):
    rv = json.loads((run / ".work" / "rpc_verify.json").read_text())
    sk = json.loads((run / ".work" / "skeleton.json").read_text())
    sym = rv.get("symbol") or "TOKEN"
    ok = [c for c in rv["checks"] if c["status"] in ("MATCH", "INFO")]
    ask = [c for c in rv["checks"] if c["status"] in ("MISMATCH", "DRIFT", "UNVERIFIED")]
    lines = [f"# ${sym} — Surf web-chat verify checklist (short)",
             "Tick: ✅ match · ❌ mismatch (note value) · ❓ Surf cannot see.", "",
             f"Already verified by free RPC at {rv['written']} (Asia/Dhaka), not sent to Surf: "
             + "; ".join(sorted({f"{c['check']} ({c['chain']})" for c in ok})) + ".", ""]
    n = 0
    drift = [c for c in ask if c["status"] == "DRIFT"]
    for c in ask:
        if c["status"] == "DRIFT":
            continue
        n += 1
        lines.append(f"{n}. [ ] {c['check']} on {c['chain']}: skeleton {c['skeleton']} vs RPC {c['rpc']} "
                     f"({c['status']}{'; ' + c['note'] if c['note'] else ''}).")
    if drift:
        n += 1
        lines.append(f"{n}. [ ] Balances moved since the run ({len(drift)} holders): "
                     + "; ".join(f"{short(c['note'].split(' · ')[0])} {c['skeleton']:,.0f}→{c['rpc']:,.0f}" for c in drift[:6])
                     + ". Confirm the moves and where the tokens went.")
    for g in sk.get("_data_gaps") or []:
        n += 1; lines.append(f"{n}. [ ] Data gap ({g.get('section')}): {g.get('reason') or g.get('why')} — Surf: what is the real value?")
    for t in list(OFFCHAIN) + list(extra):
        n += 1; lines.append(f"{n}. [ ] {t}")
    out = run / "surf-verify-checklist.auto.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out, n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir"); ap.add_argument("--extra", action="append", default=[])
    a = ap.parse_args()
    p, n = build(Path(a.run_dir), a.extra)
    print(f"{n} items → {p}")
