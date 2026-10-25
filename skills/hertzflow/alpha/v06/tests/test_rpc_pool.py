import sys, pathlib, json, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import rpc_pool as rp

def test_aliases_and_yaml():
    assert rp.urls(56) == rp.urls("bsc") == rp.urls("bnb") and len(rp.urls("bsc")) >= 3
    assert rp.urls("nochain") == []

def test_health_ordering(tmp_path, monkeypatch):
    hp = tmp_path / "h.json"; monkeypatch.setenv("HF_RPC_HEALTH", str(hp))
    base = rp.urls("bsc"); first, second = base[0], base[1]
    hp.write_text(json.dumps({first: {"ok": 0, "fail": 3, "ms": None, "ts": int(time.time()), "last": "fail"},
                              second: {"ok": 5, "fail": 0, "ms": 80, "ts": int(time.time()), "last": "ok"}}))
    o = rp.urls("bsc")
    assert o[0] == second and o[-1] == first

def test_offline(monkeypatch):
    monkeypatch.setenv("HF_RPC_OFFLINE", "1")
    assert rp.call("bsc", "eth_blockNumber", []) == (None, None)
