import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
from section_a_scope import resolve_decimals

def test_rpc_and_alpha_agree():
    assert resolve_decimals(18, 18) == (18, "rpc+alpha", None)

def test_mismatch_is_loud_rpc_wins():
    d, src, w = resolve_decimals(9, 18)
    assert d == 9 and src == "rpc" and "!=" in w

def test_rpc_failed_alpha_fallback():
    d, src, w = resolve_decimals(None, 6)
    assert d == 6 and src == "alpha_api" and w

def test_neither_is_unverified():
    d, src, w = resolve_decimals(None, None)
    assert d is None and src == "unverified_default_18" and "UNVERIFIED" in w
