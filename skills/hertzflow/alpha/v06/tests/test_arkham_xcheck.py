"""Arkham cross-check is mandatory (Desk 01 rule 2026-10-21). No live calls here."""
import sys, json, pathlib, subprocess, importlib.util, pytest
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "helpers")); sys.path.insert(0, str(V06 / "scripts"))
import arkham_xcheck as ax

def _sk(tmp):
    (tmp / ".work").mkdir(exist_ok=True)
    (tmp / ".work" / "skeleton.json").write_text(json.dumps({"meta": {"symbol": "TST", "coingecko_platforms": {"ethereum": "0xT"},
        "chain_lp_realtime": {"ethereum": {"top_holders_classified": {"unclassified": {"top": [
            {"addr": "0xA", "balance": 1}, {"addr": "0xB", "balance": 2}]}}}}}}))

def _tr(i, src="0xa"):
    return {"fromAddress": {"address": src}, "toAddress": {"address": f"0xdest{i % 7}",
            "arkhamEntity": {"name": "Binance"} if i % 7 == 0 else None},
            "unitValue": 10 + i, "blockTimestamp": "2026-10-20T10:00:00Z", "transactionHash": f"0x{i:04x}"}

def fake(path, params):
    if path.startswith("/intelligence"):
        return {"arkhamEntity": {"name": "Bitget"}} if path.endswith("0xa") else {"error": "HTTP 404"}
    if params["base"] == "0xa":
        return {"count": 250, "transfers": [_tr(i) for i in range(100)]}
    return {"count": 0, "transfers": []}

def boom(*a):
    raise AssertionError("live Arkham call in a test")

def test_live_is_default_and_separates_A_F_I(tmp_path, monkeypatch):
    monkeypatch.delenv("HF_DRY_RUN", raising=False); monkeypatch.setenv("HF_API_MODE", "live")
    _sk(tmp_path)
    d = ax.run(tmp_path, getter=fake)
    assert d["mode"] == "live" and d["status"] == "partial" and d["arkham_calls"] == 4
    assert {l["tag"] for l in d["labels"]} == {"A"} and {f["tag"] for f in d["facts"]} == {"F"}
    assert all(i["tag"] == "I" for i in d["inferences"]) and any("hub" in i["inference"] for i in d["inferences"])
    lb = {l["addr"]: l for l in d["labels"]}
    assert lb["0xb"]["entity"] == "UNKNOWN" and lb["0xb"]["reason"] == "HTTP 404"

def test_truncation_flag_at_100_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live"); monkeypatch.delenv("HF_DRY_RUN", raising=False)
    _sk(tmp_path)
    d = ax.run(tmp_path, getter=fake)
    assert d["truncated"] == ["0xa"]
    fa = {f["addr"]: f for f in d["facts"]}
    assert fa["0xa"]["truncated_at_cap"] and fa["0xa"]["lower_bound"] and not fa["0xb"]["truncated_at_cap"]

def test_fanout_spec_matches_renderer_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live"); monkeypatch.delenv("HF_DRY_RUN", raising=False)
    _sk(tmp_path)
    d = ax.run(tmp_path, getter=fake)
    assert len(d["fanout_specs"]) == 1
    spec = json.loads(pathlib.Path(d["fanout_specs"][0]).read_text())
    for k in ("headline", "source", "targets", "total", "ticker"):
        assert k in spec
    assert {"date", "time"} <= set(spec["headline"]) and {"role", "addr", "arkham_label"} <= set(spec["source"])
    assert all({"addr", "amount", "ts_utc"} <= set(t) and t["link"] in ("F", "A") for t in spec["targets"])
    fo = pathlib.Path("/workspace/style-refs/fanout.py")
    if fo.exists():  # schema check against the real renderer's reader (no render)
        src = fo.read_text()
        for k in ('spec["targets"]', 's["arkham_label"]', 't[\'ts_utc\']'):
            assert k in src

@pytest.mark.parametrize("env", [{"HF_DRY_RUN": "1"}, {"HF_API_MODE": "emulate_zero_balance"}, {"HF_API_MODE": "count"}])
def test_dry_and_emulate_only_plan(tmp_path, monkeypatch, env):
    monkeypatch.delenv("HF_DRY_RUN", raising=False); monkeypatch.setenv("HF_API_MODE", "live")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    _sk(tmp_path)
    d = ax.run(tmp_path, getter=boom)
    assert d["status"] == "plan_only" and d["arkham_calls"] == 0

def test_plan_only_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live"); monkeypatch.delenv("HF_DRY_RUN", raising=False)
    _sk(tmp_path)
    assert ax.run(tmp_path, plan_only=True, getter=boom)["status"] == "plan_only"

def test_all_errors_is_failed_and_key_never_leaks(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live"); monkeypatch.delenv("HF_DRY_RUN", raising=False)
    monkeypatch.delenv("ARKHAM_API_KEY", raising=False)
    _sk(tmp_path)
    d = ax.run(tmp_path)          # real _get, but no key → returns error without any network call
    assert d["status"] == "failed" and all(e["reason"] == "ARKHAM_API_KEY not set" for e in d["errors"])
    assert ax._scrub("abc SECRET def", "SECRET") == "abc <redacted> def"
