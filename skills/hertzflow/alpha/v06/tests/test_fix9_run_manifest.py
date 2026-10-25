import sys, pathlib, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import run_manifest as rm

def test_manifest_roundtrip(tmp_path):
    (tmp_path / ".work").mkdir(); (tmp_path / ".work" / "skeleton.json").write_text("{}")
    (tmp_path / "brief.md").write_text("x")
    p = rm.write(tmp_path, {"ca": "0xabc"})
    d = json.loads(p.read_text())
    assert d["written"].endswith("+06") and set(d["files"]) == {".work/skeleton.json", "brief.md"}
    assert rm.verify(tmp_path) == {}
    (tmp_path / "brief.md").write_text("y")
    assert rm.verify(tmp_path) == {"brief.md": "changed"}
