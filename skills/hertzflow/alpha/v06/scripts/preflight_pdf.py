#!/usr/bin/env python3
"""Perseus Desk 01 PDF gate. build_pdf.py calls pre() before building and
post() after; each failure has a NAME and a reason. Standalone:

  preflight_pdf.py RUN_DIR [--html X] [--pdf X] [--waive NAME ...]

Enforced (names):
  ARKHAM_REQUIRED   .work/arkham_xcheck.json present, status ok|partial
  DRY_RUN_FIRST     a --dry-run (count mode) of this CA was recorded
  NO_CREDIT_CAP     live run_manifest.json with budget off (HF_BUDGET=0)
  SURF_VERIFY       surf-verify.md: verdict + resolution per item; covers
                    addresses, balances, tx hashes, listing, supply, interpretation;
                    ❌/mismatch rows carry a follow-up; live figures timestamped
  FRAMES            Visual's 4 frames (cover, chip-snapshot, transfers, lp-depth)
  FANOUTS           ≥1 fan-out frame
  BRIEF_SECTIONS    brief has Limitations + Sources sections
  SOURCE_TAGS       every brief line with a number carries a source tag
  TRACE             hidden trace (trace_hidden.md) mapping numbers to file:line
  post: OVERFLOW · LINT_PRICE_TARGET · LINT_TRADE_WORDS · LINT_CLEAN_ON_GAP ·
        REPORT_SECTIONS (Style D default pack, order, Arkham wording)
Waivers (--waive NAME) are recorded in .work/preflight_pdf.json, never silent.
"""
from __future__ import annotations
import argparse, html as _html, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
FRAMES4 = {"cover": "cover", "chip-snapshot": "chip", "transfers": "transfers", "lp-depth": "lp"}
TAG_RE = re.compile(r"\[(?:A|F|I)\]|HertzFlow|Surf|Arkham|\bRPC\b|inference|Alpha API|skeleton|Source:|CoinLaunch|"
                    r"DropsTab|whitepaper|CoinGecko|pipeline", re.I)
SURF_TOPICS = {"addresses": r"0x[0-9a-f]{3,}|address", "balances": r"balance", "tx hashes": r"\btx\b|hash|0x[0-9a-f]{8,}",
               "listing date": r"listing", "supply": r"supply", "interpretation": r"interpret|inference|\[I\]|treasury|market maker"}


def _brief_lines(run: Path):
    p = run / "brief.md"
    return p.read_text(encoding="utf-8").splitlines() if p.exists() else []


def numbers_in(line: str) -> list[str]:
    t = re.sub(r"0x[0-9a-fA-F…\.]+", " ", line)                       # addresses / hashes
    t = re.sub(r"\d{4}-\d{2}-\d{2}([ T]\d{1,2}:\d{2}(:\d{2})?)?", " ", t)  # dates/times
    t = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\b", " ", t)
    t = re.sub(r"https?://\S+|\S+\.(json|md|py|csv|txt|png)\S*", " ", t)  # links / file refs
    t = re.sub(r"^\s*(#+|\d+\.)\s", " ", t)                             # list numbering / headings
    return [m for m in re.findall(r"\d[\d,\.]*%?[KMB]?", t) if any(c.isdigit() for c in m)]


def pre(run: Path) -> list[tuple[str, str]]:
    F = []
    run = Path(run)
    sk = {}
    try:
        sk = json.loads((run / ".work" / "skeleton.json").read_text())
    except Exception:
        F.append(("SKELETON", ".work/skeleton.json missing or unreadable"))
    ca = (sk.get("meta") or {}).get("contract_address")
    # ARKHAM_REQUIRED
    ap = run / ".work" / "arkham_xcheck.json"
    if not ap.exists():
        F.append(("ARKHAM_REQUIRED", f"ARKHAM REQUIRED: {ap} missing — run helpers/arkham_xcheck.py {run}"))
    else:
        try:
            ark = json.loads(ap.read_text())
            if ark.get("status") not in ("ok", "partial"):
                F.append(("ARKHAM_REQUIRED", f"ARKHAM REQUIRED: arkham_xcheck status={ark.get('status')!r} "
                          f"({ark.get('plan_only_reason') or '; '.join(str(e.get('reason')) for e in ark.get('errors') or [])[:200]})"))
        except Exception as e:
            F.append(("ARKHAM_REQUIRED", f"ARKHAM REQUIRED: unreadable ({type(e).__name__})"))
    # DRY_RUN_FIRST / NO_CREDIT_CAP
    import run_manifest as rm
    man = None
    try:
        man = json.loads((run / ".work" / "run_manifest.json").read_text())
    except Exception:
        pass
    if not rm.find_dry_run(run, ca) and not (run / "dryrun.log").exists():
        F.append(("DRY_RUN_FIRST", f"no --dry-run recorded for {ca} (.work/dry_run.json / hertzflow-cache/dry_runs)"))
    if man is None:
        F.append(("NO_CREDIT_CAP", "no .work/run_manifest.json — cannot prove the live run was uncapped"))
    elif man.get("mode") != "live":
        F.append(("NO_CREDIT_CAP", f"skeleton comes from a {man.get('mode')} run, not a live run"))
    elif man.get("budget_on", True):
        F.append(("NO_CREDIT_CAP", f"live run was credit-capped (budget on, max_credits={man.get('max_credits')}); "
                                   "Desk 01 runs use HF_BUDGET=0"))
    # SURF_VERIFY
    sv = run / "surf-verify.md"
    if not sv.exists():
        F.append(("SURF_VERIFY", "surf-verify.md missing — Surf web-chat verify is required"))
    else:
        txt = sv.read_text(encoding="utf-8")
        rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in txt.splitlines()
                if l.strip().startswith("|") and not re.fullmatch(r"[\s|:\-]+", l)]
        body = rows[1:] if rows else []
        if not body:
            F.append(("SURF_VERIFY", "surf-verify.md has no item table (| # | Item | Surf verdict | Follow-up | Final status |)"))
        else:
            bad = [r[0] for r in body if len(r) < 4 or not r[2] or not r[-1]]
            if bad:
                F.append(("SURF_VERIFY", f"items without verdict or resolution: {', '.join(bad[:8])}"))
            mm = [r[0] for r in body if re.search(r"❌|MISMATCH|NOT REPRODUCED", " ".join(r), re.I)
                  and (len(r) < 5 or r[3] in ("", "—", "-"))]
            if mm:
                F.append(("SURF_VERIFY", f"mismatch items without follow-up/resolution: {', '.join(mm)}"))
        miss = [k for k, rx in SURF_TOPICS.items() if not re.search(rx, txt, re.I)]
        if miss:
            F.append(("SURF_VERIFY", f"surf-verify.md does not cover: {', '.join(miss)}"))
        if not re.search(r"\d{1,2}:\d{2}(:\d{2})?\s*(UTC|\(?Asia/Dhaka|Dhaka|\+06)", txt):
            F.append(("SURF_VERIFY", "no timestamped live figures (HH:MM UTC / Asia/Dhaka) in surf-verify.md"))
    # FRAMES / FANOUTS
    fr = run / "frames"
    names = [p.name.lower() for p in fr.glob("*.png")] if fr.is_dir() else []
    missing = [k for k in FRAMES4 if not any(k in n for n in names)]
    if missing:
        F.append(("FRAMES", f"missing Visual frame(s): {', '.join(missing)} — NEXT: Visual"))
    if not any("fan" in n for n in names):
        F.append(("FANOUTS", "no fan-out frame in frames/ — NEXT: Visual (render .work/fanout/*.json with style-refs/fanout.py)"))
    # BRIEF_SECTIONS / SOURCE_TAGS / TRACE
    lines = _brief_lines(run)
    if not lines:
        F.append(("BRIEF_SECTIONS", "brief.md missing"))
    else:
        heads = [l for l in lines if l.startswith("## ")]
        for want, rx in (("Limitations", r"limitation"), ("Sources", r"source")):
            if not any(re.search(rx, h, re.I) for h in heads):
                F.append(("BRIEF_SECTIONS", f"brief.md has no '## {want}…' section"))
        untagged, sec_tag = [], False
        for i, l in enumerate(lines, 1):
            if l.startswith("#"):
                sec_tag = bool(TAG_RE.search(l)); continue
            if numbers_in(l) and not TAG_RE.search(l) and not sec_tag:
                untagged.append(f"brief.md:{i}")
        if untagged:
            F.append(("SOURCE_TAGS", f"{len(untagged)} line(s) with numbers but no source tag "
                                     f"(HertzFlow/Surf/Arkham [A]/[F]/[I]/inference): {', '.join(untagged[:10])}"))
    tr = next((p for p in (run / "trace_hidden.md", run / "pdf" / "trace_hidden.md") if p.exists()), None)
    if not tr or not re.search(r"\S+\.\w+:\d+", tr.read_text(encoding="utf-8")):
        F.append(("TRACE", "hidden trace (trace_hidden.md mapping each number → file:line) missing or has no file:line entries"))
    return F


def _text_of_html(h: str) -> str:
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", h, flags=re.S)
    return _html.unescape(re.sub(r"<[^>]+>", " ", h))


def lint_text(txt: str, sk: dict) -> list[tuple[str, str]]:
    F = []
    t = re.sub(r"No price target\.?", " ", txt, flags=re.I)
    pt = re.findall(r"price target|target price|\bPT\s*[:=]?\s*\$|\bTP\d?\b", t, re.I)
    if pt:
        F.append(("LINT_PRICE_TARGET", f"price-target wording: {sorted(set(pt))[:5]}"))
    tw = re.findall(r"\b(buy\w*|sell\w*|sold|pump\w*|dump\w*)\b", t, re.I)
    if tw:
        F.append(("LINT_TRADE_WORDS", f"buy/sell/pump/dump wording ×{len(tw)}: {sorted({w.lower() for w in tw})[:8]}"))
    gap = sk.get("_no_data") or any(g.get("section") == "*" for g in sk.get("_data_gaps") or [])
    if gap and re.search(r"\bCLEAN\b", txt):
        F.append(("LINT_CLEAN_ON_GAP", "report says CLEAN while the run has data gaps (_no_data)"))
    return F


REQUIRED_ORDER = ["HertzFlow (skill output only)", "Arkham cross-check", "Limitations and what's left out",
                  "Sources", "Not financial advice"]


def sections_check(txt: str, sym: str) -> list[tuple[str, str]]:
    F, miss = [], []
    cov = txt[:4000]
    for lab, rx in (("ticker", re.escape("$" + sym)), ("CA", r"\bCA\b"), ("chain", r"Chain"),
                    ("date", r"\d{4}-\d{2}-\d{2}|\d{1,2} \w{3} \d{4}"), ("state tier", r"State tier"),
                    ("RISK x/10", r"RISK\s+(\d+/10|UNKNOWN)")):
        if not re.search(rx, cov):
            miss.append(lab)
    if miss:
        F.append(("REPORT_SECTIONS", f"cover lacks: {', '.join(miss)}"))
    hf = txt.find("HertzFlow (skill output only)")
    if hf >= 0:
        blk = txt[hf:hf + 6000]
        lack = [k for k in ("State tier", "Chain state", "Chip split", "Wallet roles", "Detector") if k not in blk]
        if lack:
            F.append(("REPORT_SECTIONS", f"HertzFlow block lacks: {', '.join(lack)}"))
    pos = [txt.find(s) for s in REQUIRED_ORDER]
    for s, p in zip(REQUIRED_ORDER, pos):
        if p < 0:
            F.append(("REPORT_SECTIONS", f"missing section: {s}"))
    got = [p for p in pos if p >= 0]
    if got != sorted(got):
        F.append(("REPORT_SECTIONS", "section order must be HertzFlow → … → Arkham → Limitations → (Requester) → Sources → NFA"))
    rq = txt.find("Requester question")
    if rq >= 0 and pos[2] >= 0 and not (pos[2] < rq < (pos[3] if pos[3] >= 0 else 10 ** 9)):
        F.append(("REPORT_SECTIONS", "Requester question must come after the default pack (after Limitations, before Sources)"))
    a0 = pos[1]
    if a0 >= 0:
        nxt = min([p for p in pos[2:] if p > a0] or [len(txt)])
        if re.search(r"\bcorrect(ion|ed|s)?\b|\bsaid\b", txt[a0:nxt], re.I):
            F.append(("REPORT_SECTIONS", "Arkham section must be a side-by-side note — no 'correction' / 'said' wording"))
    return F


def post(run: Path, html_path: Path, pdf_path: Path | None, overflow: str | None, n_frames_expected: int) -> list:
    sk = json.loads((Path(run) / ".work" / "skeleton.json").read_text())
    sym = (sk.get("meta") or {}).get("symbol") or "TOKEN"
    F = []
    if overflow is not None and overflow.strip() != "NONE":
        F.append(("OVERFLOW", f"Style D overflow: {overflow.strip()[:200]}"))
    h = Path(html_path).read_text(encoding="utf-8")
    txt = _text_of_html(h)
    if pdf_path and Path(pdf_path).exists():
        try:
            txt_pdf = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True,
                                     text=True, timeout=60).stdout
            if txt_pdf.strip():
                txt = txt_pdf
        except Exception:
            pass
    F += lint_text(txt, sk)
    F += sections_check(_text_of_html(h), sym)
    imgs = len(re.findall(r"<img ", h))
    if imgs < n_frames_expected:
        F.append(("REPORT_SECTIONS", f"only {imgs} frames placed, expected {n_frames_expected}"))
    return F


def record(run: Path, stage: str, fails, waived) -> None:
    p = Path(run) / ".work" / "preflight_pdf.json"
    try:
        d = json.loads(p.read_text())
    except Exception:
        d = {}
    from run_manifest import now_str
    d[stage] = {"at": now_str(), "fail": [list(f) for f in fails if f[0] not in waived],
                "waived": [list(f) for f in fails if f[0] in waived]}
    p.write_text(json.dumps(d, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run_dir"); ap.add_argument("--html"); ap.add_argument("--pdf")
    ap.add_argument("--waive", action="append", default=[])
    a = ap.parse_args()
    run = Path(a.run_dir)
    F = pre(run)
    if a.html:
        F += post(run, Path(a.html), Path(a.pdf) if a.pdf else None, None, 0)
    for n, r in F:
        print(f"{'WAIVED' if n in a.waive else 'FAIL'} {n}: {r}")
    hard = [f for f in F if f[0] not in a.waive]
    print("PREFLIGHT OK" if not hard else f"PREFLIGHT BLOCKED ({len(hard)})")
    return 0 if not hard else 3


if __name__ == "__main__":
    sys.exit(main())
