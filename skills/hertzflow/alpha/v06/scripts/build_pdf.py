#!/usr/bin/env python3
"""Perseus fork: one-script Style D PDF from a finished run directory.

  build_pdf.py RUN_DIR [--out PDF] [--brief brief.md] [--assets styleD_assets.json]

Inputs : RUN_DIR/.work/skeleton.json (sidebar: ticker, chain, state, risk, tier),
         RUN_DIR/brief.md (one or more pages per '## ' section, auto-split),
         RUN_DIR/frames/*.png (placed on the section whose name matches the
         frame slug, the rest get their own page; *-cover.png goes on page 1).
Output : RUN_DIR/pdf/<SYM>-alpha-skill-<date>.auto.pdf by default — never
         overwrites an existing file unless --force. Prints Chrome's OVERFLOW
         report (Style D JS) and page count. Needs google-chrome + pdfinfo.
Modelled on irys-forensic/pdf/build.py and axis-forensic/pdf/build_v2.py.
"""
from __future__ import annotations
import argparse, html, json, re, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DHAKA = timezone(timedelta(hours=6))
PAGE_BUDGET = 26          # weighted lines per text page (Style D A4 landscape, 8pt body)
CH = ["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
      "--allow-file-access-from-files", "--virtual-time-budget=8000"]


def esc(t: str) -> str:
    return html.escape(t, quote=False)


def inline(t: str) -> str:
    t = esc(t)
    t = re.sub(r"`([^`]+)`", r'<span class="m">\1</span>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', t)
    return t


def md_blocks(lines: list[str]) -> list[tuple[str, int]]:
    """Markdown subset → list of (html_block, weight). Weight ≈ rendered lines."""
    out, i = [], 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1; continue
        if ln.startswith("### "):
            out.append((f'<h3 class="h3" style="font-size:10pt;margin:2mm 0 1mm">{inline(ln[4:])}</h3>', 2)); i += 1; continue
        if ln.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            if rows:  # chunks of 8 body rows, header repeated → page-splittable
                hd = '<table class="t"><tr>' + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr>"
                body = rows[1:] or [[]]
                for k in range(0, len(body), 8):
                    ch = body[k:k + 8]
                    h = hd + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in ch)
                    out.append((h + "</table>", 1 + sum(1 + len(" ".join(r)) // 140 for r in ch)))
            continue
        m = re.match(r"^(\s*)([-*]|\d+\.)\s+", ln)
        if m:
            items = []
            while i < len(lines) and re.match(r"^(\s*)([-*]|\d+\.)\s+", lines[i]):
                mm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", lines[i])
                items.append((len(mm.group(1)) // 2, mm.group(2)[0].isdigit(), mm.group(3))); i += 1
                while i < len(lines) and lines[i].startswith("  ") and lines[i].strip() and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                    items[-1] = (items[-1][0], items[-1][1], items[-1][2] + " " + lines[i].strip()); i += 1
            groups, n0 = [], 0            # one block per top-level item → page-splittable
            for it in items:
                if it[0] == 0 or not groups:
                    groups.append([]); 
                groups[-1].append(it)
            for g in groups:
                h, stack = "", []
                for lvl, num, txt in g:
                    while len(stack) > lvl + 1:
                        h += f"</{stack.pop()}>"
                    while len(stack) < lvl + 1:
                        tag = "ol" if num else "ul"; stack.append(tag)
                        st = f' start="{n0 + 1}"' if tag == "ol" and len(stack) == 1 else ""
                        h += f'<{tag}{st} class="b sm" style="margin:0 0 1mm 4mm">'
                    h += f"<li>{inline(txt)}</li>"
                while stack:
                    h += f"</{stack.pop()}>"
                n0 += 1
                out.append((h, sum(1 + len(t) // 150 for _, _, t in g)))
            continue
        para = [ln.strip()]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(\s*([-*]|\d+\.)\s+|#|\|)", lines[i]):
            para.append(lines[i].strip()); i += 1
        txt = " ".join(para)
        out.append((f'<p class="b sm">{inline(txt)}</p>', 1 + len(txt) // 160))
    return out


def sections(md: str) -> tuple[str, list[tuple[str, list[str]]]]:
    title, cur, secs = "", ("Overview", []), []
    for ln in md.splitlines():
        if ln.startswith("# ") and not title:
            title = ln[2:].strip(); continue
        if ln.startswith("## "):
            if cur[1] and any(x.strip() for x in cur[1]):
                secs.append(cur)
            cur = (ln[3:].strip(), []); continue
        cur[1].append(ln)
    if any(x.strip() for x in cur[1]):
        secs.append(cur)
    return title, secs


def paginate(blocks, budget=PAGE_BUDGET):
    pages, cur, w = [], [], 0
    for b, bw in blocks:
        if cur and w + bw > budget:
            pages.append(cur); cur, w = [], 0
        cur.append(b); w += bw
    if cur:
        pages.append(cur)
    return pages


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


class ArkhamRequired(SystemExit):
    pass


def load_arkham(run: Path) -> dict:
    """Desk 01 rule (2026-10-21): no PDF without a live Arkham cross-check."""
    p = run / ".work" / "arkham_xcheck.json"
    if not p.exists():
        raise ArkhamRequired(f"ARKHAM REQUIRED: {p} missing — run helpers/arkham_xcheck.py {run}")
    try:
        ark = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ArkhamRequired(f"ARKHAM REQUIRED: {p} unreadable ({type(e).__name__})")
    if ark.get("status") not in ("ok", "partial"):
        raise ArkhamRequired(f"ARKHAM REQUIRED: arkham_xcheck status={ark.get('status')!r} "
                             f"({ark.get('plan_only_reason') or '; '.join(str(e.get('reason')) for e in ark.get('errors') or [])[:200]})")
    return ark


def arkham_blocks(ark: dict) -> list:
    """Always-present Arkham section. Errors show UNKNOWN + reason."""
    U = '<b class="r">UNKNOWN</b>'
    b = [(f'<p class="b sm">Arkham cross-check {esc(ark.get("written", ""))} (Asia/Dhaka) · status '
          f'<b>{esc(ark.get("status", "?"))}</b> · {ark.get("arkham_calls", 0)} calls · '
          f'{len(ark.get("truncated") or [])} truncated at {ark.get("page_cap", 100)} transfers (lower bounds). '
          '[A] Arkham label · [F] on-chain fact · [I] inference.</p>', 2)]
    rows = [["Address", "Chain", "[A] Entity / label"]]
    for l in ark.get("labels") or []:
        ent = U + f' — {esc(str(l.get("reason")))}' if l.get("entity") == "UNKNOWN" else esc(str(l.get("entity")))
        rows.append([esc(l["addr"]), esc(str(l.get("chain"))), ent + (f' · {esc(l["label"])}' if l.get("label") else "")])
    frows = [["Address", "[F] Outflows", "Recipients", "Total out", "Cap"]]
    for f in ark.get("facts") or []:
        if f.get("fact") == "UNKNOWN":
            frows.append([esc(f["addr"]), U + f' — {esc(str(f.get("reason")))}', "", "", ""])
        else:
            frows.append([esc(f["addr"]), str(f["outflow_transfers"]), str(f["distinct_destinations"]),
                          f'{f["outflow_total"]:,.0f}', '<b class="r">TRUNCATED @100</b>' if f.get("truncated_at_cap") else "complete"])
    for tbl in (rows, frows):
        if len(tbl) == 1:
            tbl.append([U, "no rows returned", "", "", ""][:len(tbl[0])])
        hd = '<table class="t"><tr>' + "".join(f"<th>{c}</th>" for c in tbl[0]) + "</tr>"
        for k in range(1, len(tbl), 8):
            b.append((hd + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in tbl[k:k + 8])
                      + "</table>", 10))
    inf = ark.get("inferences") or []
    b.append(('<ul class="b sm">' + ("".join(f'<li>[I] {esc(i["addr"])}: {esc(i["inference"])}</li>' for i in inf)
                                     or "<li>[I] none drawn</li>") + "</ul>", 1 + len(inf)))
    if ark.get("errors"):
        b.append(('<p class="b sm r">Arkham errors: ' + "; ".join(
            f'{esc(str(e.get("addr")))} {esc(str(e.get("call")))}: {esc(str(e.get("reason")))}' for e in ark["errors"][:8]) + "</p>", 2))
    return b


def hertzflow_block(sk: dict, state: str, tier, risk_s: str) -> str:
    """'HertzFlow (skill output only)' — skeleton facts, no Surf/Arkham/inference."""
    from collections import Counter
    sco = sk.get("supply_chain_overhang") or {}
    if sco:
        chip = (f'operator {sco.get("operator_pct", "?")}% · relay {sco.get("relay_pct", "?")}% · '
                f'non-operator {sco.get("non_operator_pct", "?")}% ({esc(str(sco.get("supply_chain_label") or ""))})')
    else:
        rr = (sk.get("holdings_distribution") or {}).get("role_rows") or []
        chip = " · ".join(f'{esc(str(r.get("role")))} {float(r.get("pct_of_total") or 0):.2f}%' for r in rr[:6]) or "UNKNOWN — no chip data"
    roles = Counter(v.get("primary_role") for v in (sk.get("address_role_index") or {}).values() if isinstance(v, dict))
    if not roles:
        roles = Counter(w.get("monitor_role_enum") for w in sk.get("monitoring_wallets") or [])
    roles_s = " · ".join(f"{esc(str(k))} {n}" for k, n in roles.most_common(8)) or "UNKNOWN — no role index"
    waves = (sk.get("anomaly") or {}).get("waves") or []
    det = [f'{esc(re.sub(r"^[^A-Za-z]*", "", w.get("title", "")))}: {len(w.get("events") or [])} events' for w in waves]
    hoa = sk.get("hidden_operator_activity")
    if isinstance(hoa, dict) and hoa:
        det.append("hidden-operator detector: " + esc(", ".join(f"{k}={v}" for k, v in list(hoa.items())[:4]
                                                              if isinstance(v, (int, float, str, bool)))[:160]))
    rows = [("State tier", f"{esc(state)} · catalyst tier {esc(str(tier))}"),
            ("Chain state / risk", f'{esc(str(sk.get("chain_state_label") or state))} · RISK {esc(risk_s)}'),
            ("Chip split", chip), ("Wallet roles", roles_s),
            ("Detector findings", "<br>".join(det) or "none reported")]
    return ('<h2 class="h2">HertzFlow (skill output only)</h2><p class="b sm">Source: HertzFlow skeleton '
            '(.work/skeleton.json) only — no Surf, Arkham or inference in this block.</p><table class="t">'
            + "".join(f"<tr><th>{k}</th><td>{v} <i>[HertzFlow]</i></td></tr>" for k, v in rows) + "</table>")


def build(run: Path, out: Path | None, brief: Path, assets: Path, force: bool, render: bool = True,
          budget: int = PAGE_BUDGET) -> dict:
    ark = load_arkham(run)
    sk = json.loads((run / ".work" / "skeleton.json").read_text())
    meta = sk.get("meta", {})
    sym = meta.get("symbol") or "TOKEN"
    tier = (sk.get("tier_classification") or {}).get("tier") or "—"
    state = sk.get("chain_state") or "UNKNOWN"
    risk = sk.get("chain_state_risk_score")
    risk_s = f"{risk}/10" if isinstance(risk, (int, float)) else "UNKNOWN"
    chains = " · ".join(sorted({k.replace("binance-smart-chain", "BSC").title() if k != "binance-smart-chain" else "BSC"
                               for k in (meta.get("coingecko_platforms") or {meta.get("chain", "?"): 1})})) or meta.get("chain", "?")
    a = json.loads(assets.read_text())
    css = a["CSS_D"] + ("table.t{border-collapse:collapse;font-size:7.4pt;width:100%}table.t td,table.t th{border-bottom:1px solid #ccc;"
                        "padding:.8mm 1.4mm;text-align:left;vertical-align:top}")
    now = datetime.now(DHAKA)
    core = [("Ticker", f"${sym} · {meta.get('name', '')}", "w s"), ("Chains", chains, "w s"),
            ("State tier", state, "w s"), ("Catalyst tier", str(tier), ""),
            ("Risk", risk_s, "r" if risk_s != "UNKNOWN" else "")]
    if sk.get("_no_data"):
        core.append(("Data gaps", str(len(sk.get("_data_gaps") or [])), "r"))
    foot = (f"Perseus Research Lab | ${sym} forensic brief | built {now:%Y-%m-%d %H:%M} (Asia/Dhaka) | "
            "Data: HertzFlow Alpha Skill, Surf, Arkham, RPC | NFA")

    def sidebar(i, t):
        o = ['<div class="side"><span class="lab">Perseus Research Lab</span>']
        o += [f'<div class="k"><span class="lab">{x}</span><b class="{c}">{esc(v)}</b></div>' for x, v, c in core]
        o.append(f'<div class="sdiv"></div><div class="sec">{i + 1:02d} · {esc(t)}</div></div>')
        return "".join(o)

    title, secs = sections(brief.read_text(encoding="utf-8"))
    frames = sorted((run / "frames").glob("*.png")) if (run / "frames").is_dir() else []
    cover = next((f for f in frames if "cover" in f.name), None)
    used = {cover} if cover else set()

    def fig(p, mh="118mm"):
        return (f'<figure class="frame" style="width:auto"><img style="max-height:{mh};width:auto;max-width:221mm" '
                f'src="file://{p}"></figure><p class="src">Frame: {esc(p.name)}</p>')

    pages = []
    cov = f'<div class="cvt"><h1 class="hl" style="font-size:18pt;margin:0 0 2mm">{inline(title or "$" + sym)}</h1></div>'
    if cover:
        cov += fig(cover, "105mm")
    cov += (f'<p class="b sm" style="font-family:\'IBM Plex Mono\',monospace">${esc(sym)} · CA {esc(meta.get("contract_address", ""))} · '
            f'Chain {esc(chains)} · {now:%Y-%m-%d} (Asia/Dhaka) · State tier {esc(state)} · RISK {esc(risk_s)} · '
            f'Alpha listing {esc(str(meta.get("alpha_listing_date_utc")))} UTC</p>')
    if sk.get("_data_gaps"):
        cov += '<p class="b sm r"><b>Data gaps:</b> ' + "; ".join(esc(g.get("reason") or g.get("why", "")) for g in sk["_data_gaps"]) + "</p>"
    pages.append(("Cover", cov))
    pages.append(("HertzFlow (skill output only)", hertzflow_block(sk, state, tier, risk_s)))

    def kind(n):
        n = n.lower()
        return ("lim" if "limitation" in n else "req" if "requester" in n else "src" if re.search(r"\bsources?\b", n)
                else "ark" if "arkham" in n else "body")
    def add_sec(name, lines, frames_ok=True):
        s_ = slug(name)
        mine = [f for f in frames if frames_ok and f not in used and any(w in f.stem.lower() for w in s_.split("-") if len(w) > 4)]
        for k, chunk in enumerate(paginate(md_blocks(lines), budget)):
            pages.append((name if k == 0 else f"{name} (cont.)",
                          f'<h2 class="h2">{inline(name)}{" (cont.)" if k else ""}</h2>' + "".join(chunk)))
        for f in mine:
            used.add(f); pages.append((name, f'<h2 class="h2">{inline(name)}</h2>' + fig(f)))
    for name, lines in secs:
        if kind(name) == "body":
            add_sec(name, lines)
    for f in frames:  # Visual's 4 frames + fan-outs not already placed
        if f not in used:
            nm = re.sub(r"^[A-Z0-9]+-", "", f.stem).replace("-", " ")
            used.add(f); pages.append((nm.title(), f'<h2 class="h2">{esc(nm.title())}</h2>' + fig(f)))
    ark_secs = [(n, l) for n, l in secs if kind(n) == "ark"]
    blocks = arkham_blocks(ark) + [b for _, l in ark_secs for b in md_blocks(l)]
    for k, chunk in enumerate(paginate(blocks, budget)):
        pages.append(("Arkham cross-check" + (" (cont.)" if k else ""),
                      f'<h2 class="h2">Arkham cross-check{" (cont.)" if k else ""}</h2>'
                      + ('<p class="b sm">Side-by-side note: Arkham view next to the HertzFlow view; neither overrides the other.</p>' if not k else "")
                      + "".join(chunk)))
    for want in ("lim", "req", "src"):
        for name, lines in secs:
            if kind(name) == want:
                add_sec("Limitations and what's left out" if want == "lim" else name, lines, frames_ok=False)
    nfa = '<p class="b"><b>Not financial advice.</b> No price target. Research notes only.</p>'
    if kind(pages[-1][0]) == "src":
        pages[-1] = (pages[-1][0], pages[-1][1] + nfa)
    else:
        pages.append(("NFA", nfa))
    body = "".join(
        f'<div class="pg p{i + 1}">{sidebar(i, t)}<div class="content"><div class="kick">Forensic brief · '
        f'{now:%d %b %Y} · {esc(t)}</div>{b}</div><div class="foot">{foot}<span class="pn">p.{i + 1}</span></div></div>'
        for i, (t, b) in enumerate(pages))
    doc = f'<!doctype html><html><head><meta charset="utf-8"><title>${sym} forensic brief</title><style>{css}</style>{a["JS"]}</head><body>{body}</body></html>'
    out = out or run / "pdf" / f"{sym}-alpha-skill-{now:%Y-%m-%d}.auto.pdf"
    if out.exists() and not force:
        raise SystemExit(f"refusing to overwrite {out} (use --out or --force)")
    out.parent.mkdir(parents=True, exist_ok=True)
    hp = out.with_suffix(".html"); hp.write_text(doc, encoding="utf-8")
    res = {"html": str(hp), "pdf": str(out), "pages_built": len(pages), "overflow": None, "pdf_pages": None}
    if not render:
        return res
    dom = subprocess.run(CH + ["--dump-dom", f"file://{hp}"], capture_output=True, text=True, timeout=120).stdout
    m = re.search(r'<pre id="OVERFLOW"[^>]*>(.*?)</pre>', dom, re.S)
    res["overflow"] = html.unescape(m.group(1)).strip() if m else "??"
    subprocess.run(CH + ["--no-pdf-header-footer", f"--print-to-pdf={out}", f"file://{hp}"], capture_output=True, timeout=180)
    info = subprocess.run(["pdfinfo", str(out)], capture_output=True, text=True).stdout
    mm = re.search(r"Pages:\s+(\d+)", info)
    res["pdf_pages"] = int(mm.group(1)) if mm else None
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--out"); ap.add_argument("--brief")
    ap.add_argument("--assets", default=str(HERE / "assets" / "styleD_assets.json"))
    ap.add_argument("--force", action="store_true"); ap.add_argument("--html-only", action="store_true")
    ap.add_argument("--waive", action="append", default=[], help="waive a named preflight rule (logged)")
    a = ap.parse_args()
    run = Path(a.run_dir).resolve()
    import preflight_pdf as pf
    fails = pf.pre(run)
    pf.record(run, "pre", fails, set(a.waive)) if (run / ".work").is_dir() else None
    hard = [f for f in fails if f[0] not in a.waive]
    for n, why in fails:
        print(f"{'WAIVED' if n in a.waive else 'PREFLIGHT FAIL'} {n}: {why}", file=sys.stderr)
    if hard:
        print(f"PDF BLOCKED by preflight ({len(hard)}): {', '.join(sorted({n for n, _ in hard}))}", file=sys.stderr)
        return 3
    args = (run, Path(a.out) if a.out else None, Path(a.brief) if a.brief else run / "brief.md", Path(a.assets))
    budget, force = PAGE_BUDGET, a.force
    for _ in range(4):  # auto-shrink pages until Style D reports no overflow
        r = build(*args, force, render=not a.html_only, budget=budget)
        r["page_budget"] = budget
        if a.html_only or not r["overflow"] or "overflow" not in r["overflow"]:
            break
        budget, force = int(budget * 0.8), True
    n_fr = len(list((run / "frames").glob("*.png"))) if (run / "frames").is_dir() else 0
    pfails = pf.post(run, Path(r["html"]), None if a.html_only else Path(r["pdf"]),
                     None if a.html_only else r["overflow"], n_fr)
    pf.record(run, "post", pfails, set(a.waive))
    for n, why in pfails:
        print(f"{'WAIVED' if n in a.waive else 'POSTFLIGHT FAIL'} {n}: {why}", file=sys.stderr)
    if [f for f in pfails if f[0] not in a.waive]:
        if not a.html_only and Path(r["pdf"]).exists():
            b = Path(r["pdf"]).with_suffix(".BLOCKED.pdf"); Path(r["pdf"]).replace(b); r["pdf"] = str(b)
        r["blocked"] = sorted({n for n, _ in pfails if n not in a.waive})
        print(json.dumps(r, indent=1))
        return 4
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
