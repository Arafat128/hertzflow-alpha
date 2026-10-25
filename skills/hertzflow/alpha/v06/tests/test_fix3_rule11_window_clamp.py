"""Fix 3: outflow ceiling must never sit before the mint day."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
from rule_11_backward_trace import outflow_window_ceiling

def test_mint_before_listing_unchanged():
    assert outflow_window_ceiling("2026-03-01", "2026-01-15") == ("2026-03-01", False)

def test_mint_after_listing_extended():
    c, ext = outflow_window_ceiling("2026-03-01", "2026-03-05", today="2026-10-26")
    assert ext and c == "2026-03-19" and c >= "2026-03-05"

def test_extension_never_past_today():
    c, ext = outflow_window_ceiling("2026-10-20", "2026-10-24", today="2026-10-26")
    assert ext and c == "2026-10-26"

def test_missing_mint_day():
    assert outflow_window_ceiling("2026-03-01", None) == ("2026-03-01", False)
