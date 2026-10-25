import sys, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import update_check

def test_auto_update_disabled(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: called.append(a) or None)
    ok, reason = update_check._run_auto_update("abc", tmp_path / "i", tmp_path / "c")
    assert (ok, reason) == (False, "disabled_in_fork")
    assert called == []

def test_no_npx_instruction_in_lang():
    root = pathlib.Path(__file__).resolve().parents[1] / "lang"
    for f in root.glob("*.json"):
        assert "运行 `npx skills update" not in f.read_text()
        assert "Run `npx skills update" not in f.read_text()
