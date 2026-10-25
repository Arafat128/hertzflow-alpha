import sys, json, pathlib, pytest
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "scripts"))
import build_pdf as bp

def _run(tmp):
    (tmp / ".work").mkdir(); (tmp / "frames").mkdir()
    (tmp / ".work" / "skeleton.json").write_text(json.dumps({"meta": {"symbol": "TST", "name": "Test", "chain": "BSC"},
        "chain_state": "UNKNOWN", "chain_state_risk_score": None, "_no_data": True,
        "_data_gaps": [{"section": "*", "why": "0 successful paid calls"}]}))
    (tmp / "frames" / "TST-00-cover.png").write_bytes(b"\x89PNG")
    (tmp / "frames" / "TST-01-chip-snapshot.png").write_bytes(b"\x89PNG")
    md = "# T\n## 3 FACTS\n" + "\n".join(f"{i}. **fact** {'x'*300}" for i in range(1, 12)) + \
         "\n## CHIP SNAPSHOT\n| a | b |\n|---|---|\n" + "\n".join(f"| {i} | y |" for i in range(30))
    (tmp / "brief.md").write_text(md)

def test_html_build_paginates_and_flags_gaps(tmp_path):
    _run(tmp_path)
    r = bp.build(tmp_path, None, tmp_path / "brief.md", V06 / "assets" / "styleD_assets.json", False, render=False)
    h = pathlib.Path(r["html"]).read_text()
    assert r["pages_built"] >= 5 and "Data gaps" in h and "UNKNOWN" in h and "chip-snapshot" in h
    assert r["pdf"].endswith(".auto.pdf")
    pathlib.Path(r["pdf"]).write_text("x")
    with pytest.raises(SystemExit):
        bp.build(tmp_path, None, tmp_path / "brief.md", V06 / "assets" / "styleD_assets.json", False, render=False)
