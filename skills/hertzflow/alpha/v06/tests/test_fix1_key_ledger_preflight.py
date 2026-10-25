"""Fix 1: persistent PAID_BALANCE_ZERO ledger + 0-credit preflight (fake keys only)."""
import os, sys, json, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import api_gateway as gw

def _pool(monkeypatch, tmp_path, n=2):
    monkeypatch.setenv("HF_KEY_LEDGER", str(tmp_path / "ledger.json"))
    for i in range(4, 12):
        monkeypatch.delenv(f"SURF_API_KEY_{i}", raising=False)
    for i in range(4, 4 + n):
        monkeypatch.setenv(f"SURF_API_KEY_{i}", f"fake-{i}")
    monkeypatch.delenv("SURF_API_KEY", raising=False)

def test_ledger_never_stores_value(monkeypatch, tmp_path):
    _pool(monkeypatch, tmp_path)
    gw.record_pbz("SURF_API_KEY_4", "fake-4")
    raw = (tmp_path / "ledger.json").read_text()
    assert "fake-4" not in raw and "SURF_API_KEY_4" in raw

def test_preflight_aborts_when_all_known_empty(monkeypatch, tmp_path):
    _pool(monkeypatch, tmp_path)
    gw.record_pbz("SURF_API_KEY_4", "fake-4"); gw.record_pbz("SURF_API_KEY_5", "fake-5")
    gw._init_keys()
    ok, msg = gw.preflight()
    assert not ok and "PAID_BALANCE_ZERO" in msg and "fake-" not in msg

def test_preflight_ok_with_one_alive_and_skips_dead(monkeypatch, tmp_path):
    _pool(monkeypatch, tmp_path)
    gw.record_pbz("SURF_API_KEY_4", "fake-4")
    gw._init_keys()
    ok, msg = gw.preflight()
    assert ok and "SURF_API_KEY_5" in msg
    assert gw._KEYS.current()[0] == "SURF_API_KEY_5"

def test_new_key_value_resets(monkeypatch, tmp_path):
    _pool(monkeypatch, tmp_path)
    gw.record_pbz("SURF_API_KEY_4", "old-value")
    assert not gw.ledger_dead("SURF_API_KEY_4", "fake-4")

def test_ttl_expiry(monkeypatch, tmp_path):
    _pool(monkeypatch, tmp_path)
    gw.record_pbz("SURF_API_KEY_4", "fake-4")
    d = json.loads((tmp_path / "ledger.json").read_text()); d["SURF_API_KEY_4"]["ts"] = time.time() - 90000
    (tmp_path / "ledger.json").write_text(json.dumps(d))
    assert not gw.ledger_dead("SURF_API_KEY_4", "fake-4")
