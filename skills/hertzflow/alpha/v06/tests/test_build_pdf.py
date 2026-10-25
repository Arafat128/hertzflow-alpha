import sys, json, pathlib, subprocess, pytest
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "scripts"))
import build_pdf as bp
A = V06 / "assets" / "styleD_assets.json"

def _run(tmp):
    (tmp / ".work").mkdir(); (tmp / "frames").mkdir()
    (tmp / ".work" / "skeleton.json").write_text(json.dumps({"meta": {"symbol": "TST", "name": "Test", "chain": "BSC"},
        "chain_state": "UNKNOWN", "chain_state_risk_score": None, "_no_data": True,
        "_data_gaps": [{"section": "*", "reason": "0 successful paid calls"}]}))
    (tmp / "frames" / "TST-00-cover.png").write_bytes(b"\x89PNG")
    (tmp / "frames" / "TST-01-chip-snapshot.png").write_bytes(b"\x89PNG")
    md = "# T\n## 3 FACTS\n" + "\n".join(f"{i}. **fact** {'x'*300}" for i in range(1, 12)) + \
         "\n## CHIP SNAPSHOT\n| a | b |\n|---|---|\n" + "\n".join(f"| {i} | y |" for i in range(30))
    (tmp / "brief.md").write_text(md)

def _ark(tmp, status="partial"):
    (tmp / ".work" / "arkham_xcheck.json").write_text(json.dumps({"status": status, "written": "2026-10-26 02:30:00+06",
        "arkham_calls": 4, "page_cap": 100, "truncated": ["0xaaa"],
        "labels": [{"addr": "0xaaa", "chain": "bsc", "entity": "Bitget", "label": None, "tag": "A"},
                   {"addr": "0xbbb", "chain": "bsc", "entity": "UNKNOWN", "label": None, "reason": "HTTP 404", "tag": "A"}],
        "facts": [{"addr": "0xaaa", "tag": "F", "outflow_transfers": 100, "distinct_destinations": 7,
                   "outflow_total": 5000.0, "truncated_at_cap": True},
                  {"addr": "0xbbb", "tag": "F", "fact": "UNKNOWN", "reason": "HTTP 500"}],
        "inferences": [{"addr": "0xaaa", "tag": "I", "inference": "distribution hub: 7 distinct recipients"}],
        "errors": [{"addr": "0xbbb", "call": "intel", "reason": "HTTP 404"}]}))

def test_pdf_blocked_without_arkham(tmp_path):
    _run(tmp_path)
    with pytest.raises(bp.ArkhamRequired, match="ARKHAM REQUIRED"):
        bp.build(tmp_path, None, tmp_path / "brief.md", A, False, render=False)
    p = subprocess.run([sys.executable, str(V06 / "scripts" / "build_pdf.py"), str(tmp_path), "--html-only"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode != 0 and "ARKHAM REQUIRED" in p.stderr

@pytest.mark.parametrize("status", ["failed", "plan_only"])
def test_pdf_blocked_on_failed_or_plan_only(tmp_path, status):
    _run(tmp_path); _ark(tmp_path, status)
    with pytest.raises(bp.ArkhamRequired):
        bp.build(tmp_path, None, tmp_path / "brief.md", A, False, render=False)

def test_arkham_section_present_with_unknown_and_truncation(tmp_path):
    _run(tmp_path); _ark(tmp_path)
    r = bp.build(tmp_path, None, tmp_path / "brief.md", A, False, render=False)
    h = pathlib.Path(r["html"]).read_text()
    assert "Arkham cross-check" in h and "Bitget" in h and "TRUNCATED @100" in h
    assert "UNKNOWN</b> — HTTP 404" in h and "UNKNOWN</b> — HTTP 500" in h and "[I] 0xaaa" in h

def test_html_build_paginates_and_flags_gaps(tmp_path):
    _run(tmp_path); _ark(tmp_path, "ok")
    r = bp.build(tmp_path, None, tmp_path / "brief.md", A, False, render=False)
    h = pathlib.Path(r["html"]).read_text()
    assert r["pages_built"] >= 5 and "Data gaps" in h and "UNKNOWN" in h and "chip-snapshot" in h
    pathlib.Path(r["pdf"]).write_text("x")
    with pytest.raises(SystemExit):
        bp.build(tmp_path, None, tmp_path / "brief.md", A, False, render=False)
