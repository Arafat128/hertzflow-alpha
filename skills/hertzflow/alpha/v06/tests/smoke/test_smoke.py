"""Smoke (0 Surf credits): opt-in with HF_SMOKE=1 (needs network for free APIs).
1) dry-run plan matches golden paid-call counts  2) emulate_zero_balance → UNKNOWN."""
import json, os, re, subprocess, sys, pathlib, pytest
V06 = pathlib.Path(__file__).resolve().parents[2]
G = json.loads((pathlib.Path(__file__).parent / "golden.json").read_text())
pytestmark = pytest.mark.skipif(os.environ.get("HF_SMOKE") != "1", reason="set HF_SMOKE=1")
TOT = re.compile(r"RUN TOTAL mode=(\S+) paid: (\d+) requested / (\d+) sent .*est_if_billed=(\d+)")

def _run(ca, mode, out):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SURF_API_KEY", "ARKHAM"))}
    env.update(HF_API_MODE=mode, BINANCE_ALPHA_NO_AUTO_UPDATE="1")
    args = [sys.executable, str(V06 / "forensic_pipeline.py"), ca, "--no-cache", "--lang", "en", "--out-dir", str(out)]
    if mode == "count":
        args.insert(3, "--dry-run")
    p = subprocess.run(args, capture_output=True, text=True, env=env, timeout=900)
    m = TOT.search(p.stdout + p.stderr)
    assert m, (p.stdout + p.stderr)[-2000:]
    return m, out / ".work" / "skeleton.json"

@pytest.mark.parametrize("sym", ["IRYS", "AXIS"])
def test_dry_run_matches_golden(sym, tmp_path):
    m, _ = _run(G[sym]["ca"], "count", tmp_path)
    assert m.group(3) == "0"                       # nothing sent
    assert int(m.group(2)) == G[sym]["requested"] and int(m.group(4)) == G[sym]["est_if_billed"]

def test_zero_balance_is_unknown(tmp_path):
    m, sk = _run(G["IRYS"]["ca"], "emulate_zero_balance", tmp_path)
    s = json.loads(sk.read_text())
    assert s["chain_state"] == "UNKNOWN" and s["chain_state_risk_score"] is None and s["_no_data"]

def test_zero_balance_report_says_unknown(tmp_path):
    _, sk = _run(G["IRYS"]["ca"], "emulate_zero_balance", tmp_path)
    fill = tmp_path / "fill.json"
    fill.write_text(sk.read_text(encoding="utf-8").replace("<LLM_NARRATIVE_PLACEHOLDER>", "smoke"), encoding="utf-8")
    out = tmp_path / "r.md"
    subprocess.run([sys.executable, str(V06 / "render_report.py"), "--skeleton", str(sk), "--filled", str(fill),
                    "--out", str(out), "--lang", "en"], capture_output=True, text=True, timeout=120)
    md = out.read_text(encoding="utf-8")
    assert "On-chain state: UNKNOWN" in md and "No significant trigger (risk score 0/10)" not in md
