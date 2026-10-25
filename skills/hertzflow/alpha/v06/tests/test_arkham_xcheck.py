import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import arkham_xcheck as ax

def _sk(tmp):
    (tmp / ".work").mkdir()
    (tmp / ".work" / "skeleton.json").write_text(json.dumps({"meta": {"coingecko_platforms": {"ethereum": "0xT"},
        "chain_lp_realtime": {"ethereum": {"top_holders_classified": {"unclassified": {"top": [
            {"addr": "0xA", "balance": 1}, {"addr": "0xB", "balance": 2}]}}}}}}))

def test_plan_only_makes_no_calls(tmp_path):
    _sk(tmp_path)
    d = ax.run(tmp_path, getter=lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    assert d["mode"] == "plan_only" and d["arkham_calls"] == 0 and len(d["rows"]) == 2

def test_live_flags_truncation(tmp_path):
    _sk(tmp_path)
    def g(path, params):
        if path.startswith("/intelligence"):
            return {"arkhamEntity": {"name": "Bitget"}}
        n = 100 if params["base"] == "0xA" else 7
        return {"count": n, "transfers": [{}] * n}
    d = ax.run(tmp_path, live=True, getter=g)
    assert d["truncated"] == ["0xA"] and d["arkham_calls"] == 4 and d["rows"][0]["entity"] == "Bitget"

def test_no_key_error_never_leaks(monkeypatch):
    monkeypatch.delenv("ARKHAM_API_KEY", raising=False)
    assert ax._get("/x") == {"error": "ARKHAM_API_KEY not set"}
    assert ax._scrub("abc SECRET def", "SECRET") == "abc <redacted> def"
