"""Fix 2: rule_11 step1 retries an all-errored fast slice once when transient,
never in dry-run / breaker-open; errors still return lookup_ok=False."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import rule_11_backward_trace as r11

def _fake(seq):
    calls = []
    def f(ca, floor, workdir, ceiling=None):
        calls.append((floor, ceiling))
        return seq[min(len(calls) - 1, len(seq) - 1)]
    return f, calls

ROW = [{"deployer": "0x" + "1" * 40, "amt": 1.0, "first_mint_ts": 1700000000, "n_mints": 1}]

def test_retry_recovers(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_API_MODE", "live")
    f, calls = _fake([([], "err", 1, 1), (ROW, "ok", 0, 1)])
    monkeypatch.setattr(r11, "fetch_mint_event_chunked", f)
    monkeypatch.setattr(r11, "_r11_transient_retry_allowed", lambda: True)
    rows, diag, ok = r11.fetch_mint_event_with_fast_path(
        ca="0x" + "a" * 40, listing_date="2026-01-10", mint_floor="2024-01-10", workdir=tmp_path)
    assert ok and rows == ROW and "after retry" in diag and len(calls) == 2

def test_no_retry_when_blocked(monkeypatch, tmp_path):
    f, calls = _fake([([], "err", 1, 1)])
    monkeypatch.setattr(r11, "fetch_mint_event_chunked", f)
    monkeypatch.setattr(r11, "_r11_transient_retry_allowed", lambda: False)
    rows, diag, ok = r11.fetch_mint_event_with_fast_path(
        ca="0x" + "a" * 40, listing_date="2026-01-10", mint_floor="2024-01-10", workdir=tmp_path)
    assert not ok and rows == [] and len(calls) == 1

def test_retry_disallowed_in_dry_run(monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "count")
    assert r11._r11_transient_retry_allowed() is False

def test_retry_hard_cap(monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live"); monkeypatch.setenv("HF_R11_RETRY", "50")
    monkeypatch.setattr(r11, "_R11_RETRIES_USED", 0)
    import api_gateway as gw
    monkeypatch.setattr(gw, "S", None); monkeypatch.setattr(gw, "_KEYS", None)
    got = [r11._r11_transient_retry_allowed() for _ in range(5)]
    assert got == [True, False, False, False, False]
