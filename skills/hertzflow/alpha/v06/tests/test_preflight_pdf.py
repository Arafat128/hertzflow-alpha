"""One test per Desk 01 preflight gate (no network, 0 Surf credits)."""
import sys, json, pathlib, subprocess, pytest
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "scripts")); sys.path.insert(0, str(V06 / "helpers"))
import preflight_pdf as pf, build_pdf as bp, run_manifest as rm
A = V06 / "assets" / "styleD_assets.json"
CA = "0x" + "ab" * 20

SURF = """# Surf verify · 2026-10-26 02:10 (Asia/Dhaka)
| # | Item | Surf verdict / values | Our follow-up | Final status |
|---|---|---|---|---|
| 1 | Deployer address 0xabcabc | ✅ matches | — | CONFIRMED |
| 2 | Treasury balance 1.2M at 02:05 UTC | ✅ live | — | CONFIRMED (live) |
| 3 | tx hash 0xdeadbeef01 | ❌ not found | re-checked on RPC, tx exists | RESOLVED |
| 4 | Alpha listing date | ✅ 2026-09-01 | — | CONFIRMED |
| 5 | Total supply 10B | ✅ | — | CONFIRMED |
| 6 | Interpretation: treasury-like Safe | ⚠ plausible | — | INFERENCE kept |
"""

BRIEF = """# $TST forensic brief
## Chip snapshot
Operator holds 12.5% [HertzFlow]
Surf confirms supply 10B (Surf)
## Limitations and what's left out
Wallet labels beyond 100 transfers are lower bounds [F]
## Requester question
Is the treasury moving? 0 outflows [A] [F]
## Sources
HertzFlow skeleton · Surf · Arkham
"""


def good(tmp, monkeypatch):
    monkeypatch.setenv("HF_DRYRUN_ROOT", str(tmp / "dry"))
    w = tmp / ".work"; w.mkdir(); (tmp / "frames").mkdir()
    (w / "skeleton.json").write_text(json.dumps({"meta": {"symbol": "TST", "name": "Test", "chain": "BSC", "contract_address": CA},
        "chain_state": "DISTRIBUTING", "chain_state_risk_score": 6, "tier_classification": {"tier": "B"},
        "supply_chain_overhang": {"operator_pct": 12.5, "relay_pct": 3, "non_operator_pct": 84.5},
        "address_role_index": {"0x1": {"primary_role": "treasury"}},
        "anomaly": {"waves": [{"title": "Wave 3: Recent 72h", "events": [{}, {}]}]}}))
    (w / "run_manifest.json").write_text(json.dumps({"ca": CA, "mode": "live", "budget_on": False, "max_credits": None}))
    rm.record_dry_run(tmp, CA, "count")
    (w / "arkham_xcheck.json").write_text(json.dumps({"status": "ok", "labels": [], "facts": [], "inferences": [], "truncated": []}))
    for n in ("00-cover", "01-chip-snapshot", "02-transfers", "03-lp-depth", "fan-1-treasury"):
        (tmp / "frames" / f"TST-{n}.png").write_bytes(b"\x89PNG")
    (tmp / "surf-verify.md").write_text(SURF)
    (tmp / "brief.md").write_text(BRIEF)
    (tmp / "trace_hidden.md").write_text("12.5% → .work/skeleton.json:1\n10B → surf-verify.md:8\n")
    return tmp


def names(F):
    return {n for n, _ in F}


def test_good_run_passes_pre_and_post(tmp_path, monkeypatch):
    run = good(tmp_path, monkeypatch)
    assert pf.pre(run) == []
    r = bp.build(run, None, run / "brief.md", A, False, render=False)
    F = pf.post(run, pathlib.Path(r["html"]), None, "NONE", 5)
    assert F == [], F


@pytest.mark.parametrize("gate,breaker", [
    ("ARKHAM_REQUIRED", lambda r: (r / ".work/arkham_xcheck.json").unlink()),
    ("DRY_RUN_FIRST", lambda r: [p.unlink() for p in [r / ".work/dry_run.json", *(r / "dry").glob("*.json")]]),
    ("NO_CREDIT_CAP", lambda r: (r / ".work/run_manifest.json").write_text(json.dumps({"mode": "live", "budget_on": True, "max_credits": "400"}))),
    ("NO_CREDIT_CAP", lambda r: (r / ".work/run_manifest.json").write_text(json.dumps({"mode": "count"}))),
    ("SURF_VERIFY", lambda r: (r / "surf-verify.md").unlink()),
    ("SURF_VERIFY", lambda r: (r / "surf-verify.md").write_text(SURF.replace("| re-checked on RPC, tx exists | RESOLVED", "| — | "))),
    ("SURF_VERIFY", lambda r: (r / "surf-verify.md").write_text(SURF.replace("Total supply 10B", "Cap"))),
    ("SURF_VERIFY", lambda r: (r / "surf-verify.md").write_text(SURF.replace("02:10 (Asia/Dhaka)", "").replace("at 02:05 UTC", ""))),
    ("FRAMES", lambda r: (r / "frames/TST-03-lp-depth.png").unlink()),
    ("FANOUTS", lambda r: (r / "frames/TST-fan-1-treasury.png").unlink()),
    ("BRIEF_SECTIONS", lambda r: (r / "brief.md").write_text(BRIEF.replace("## Limitations and what's left out", "## Misc"))),
    ("SOURCE_TAGS", lambda r: (r / "brief.md").write_text(BRIEF + "\nUnsourced 42% figure\n")),
    ("TRACE", lambda r: (r / "trace_hidden.md").unlink()),
])
def test_each_pre_gate(tmp_path, monkeypatch, gate, breaker):
    run = good(tmp_path, monkeypatch); breaker(run)
    assert gate in names(pf.pre(run))


def _post_txt(tmp_path, monkeypatch, mutate):
    run = good(tmp_path, monkeypatch)
    r = bp.build(run, None, run / "brief.md", A, False, render=False)
    hp = pathlib.Path(r["html"]); hp.write_text(mutate(hp.read_text()))
    return names(pf.post(run, hp, None, "NONE", 5))


def test_post_lints(tmp_path, monkeypatch):
    assert "LINT_PRICE_TARGET" in _post_txt(tmp_path, monkeypatch, lambda h: h.replace("</body>", "<p>price target $2</p></body>"))


def test_post_trade_words(tmp_path, monkeypatch):
    assert "LINT_TRADE_WORDS" in _post_txt(tmp_path, monkeypatch, lambda h: h.replace("</body>", "<p>whales dump soon, buy</p></body>"))


def test_post_clean_on_gap(tmp_path, monkeypatch):
    run = good(tmp_path, monkeypatch)
    sk = json.loads((run / ".work/skeleton.json").read_text()); sk["_no_data"] = True
    (run / ".work/skeleton.json").write_text(json.dumps(sk))
    r = bp.build(run, None, run / "brief.md", A, False, render=False)
    hp = pathlib.Path(r["html"]); hp.write_text(hp.read_text().replace("</body>", "<p>Verdict CLEAN</p></body>"))
    assert "LINT_CLEAN_ON_GAP" in names(pf.post(run, hp, None, "NONE", 5))


def test_post_overflow(tmp_path, monkeypatch):
    run = good(tmp_path, monkeypatch)
    r = bp.build(run, None, run / "brief.md", A, False, render=False)
    assert "OVERFLOW" in names(pf.post(run, pathlib.Path(r["html"]), None, "p.3 overflow 4mm", 5))


def test_post_arkham_wording(tmp_path, monkeypatch):
    assert "REPORT_SECTIONS" in _post_txt(tmp_path, monkeypatch,
        lambda h: h.replace("Side-by-side note", "Arkham correction: HertzFlow said"))


def test_post_missing_hertzflow_block(tmp_path, monkeypatch):
    assert "REPORT_SECTIONS" in _post_txt(tmp_path, monkeypatch,
        lambda h: h.replace("HertzFlow (skill output only)", "Overview"))


def test_built_order_requester_after_default_pack(tmp_path, monkeypatch):
    run = good(tmp_path, monkeypatch)
    t = pf._text_of_html(pathlib.Path(bp.build(run, None, run / "brief.md", A, False, render=False)["html"]).read_text())
    i = [t.find(s) for s in ("HertzFlow (skill output only)", "Arkham cross-check", "Limitations and what's left out",
                             "Requester question", "Sources", "Not financial advice")]
    assert -1 not in i and i == sorted(i)


def test_cli_blocks_with_named_reasons(tmp_path, monkeypatch):
    run = good(tmp_path, monkeypatch); (run / "trace_hidden.md").unlink(); (run / "frames/TST-02-transfers.png").unlink()
    p = subprocess.run([sys.executable, str(V06 / "scripts/build_pdf.py"), str(run), "--html-only"],
                       capture_output=True, text=True, timeout=60, env={**__import__("os").environ})
    assert p.returncode == 3 and "TRACE" in p.stderr and "NEXT: Visual" in p.stderr
    p = subprocess.run([sys.executable, str(V06 / "scripts/build_pdf.py"), str(run), "--html-only",
                        "--waive", "TRACE", "--waive", "FRAMES"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert json.loads((run / ".work/preflight_pdf.json").read_text())["pre"]["waived"]


def test_live_max_credits_refused():
    p = subprocess.run([sys.executable, str(V06 / "forensic_pipeline.py"), CA, "--max-credits", "400"],
                       capture_output=True, text=True, timeout=60, env={**__import__("os").environ, "HF_API_MODE": "live"})
    assert p.returncode != 0 and "--max-credits is not allowed" in p.stderr
