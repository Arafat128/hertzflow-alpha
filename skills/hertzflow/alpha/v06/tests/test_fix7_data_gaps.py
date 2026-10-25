"""Fix 7: 0 successful paid calls → chain_state UNKNOWN, never a CLEAN default.
Replays the shipped $BR skeleton shape (CLEAN/0 with successful_calls=0)."""
import sys, pathlib, json
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06)); sys.path.insert(0, str(V06 / "helpers"))
import forensic_pipeline as fp
from render_report import _derive_chain_state_neutral_5tier as ds5

def _skel(calls):
    return {"chain_state": "CLEAN", "chain_state_label": "clean", "chain_state_risk_score": 0,
            "_surf_credits": {"credits_used": 0.0, "successful_calls": calls}, "meta": {}}

def test_br_shape_becomes_unknown(monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live")
    s = fp.apply_data_gaps(_skel(0), {"_trace_error": "Step 1 (find mint) all surf chunks failed"})
    assert s["chain_state"] == "UNKNOWN" and s["chain_state_risk_score"] is None
    assert s["_no_data"] and s["chain_state_default_was"] == "CLEAN"
    assert {g["section"] for g in s["_data_gaps"]} == {"*", "rule_11"}
    assert ds5(s)["subtype"] == "UNKNOWN"

def test_measured_run_untouched(monkeypatch):
    monkeypatch.setenv("HF_API_MODE", "live")
    s = fp.apply_data_gaps(_skel(70), {})
    assert s["chain_state"] == "CLEAN" and s["chain_state_measured"] and s["_data_gaps"] == []

def test_truncation_and_decimals_are_listed(monkeypatch):
    sk = _skel(10); sk["meta"]["decimals_warning"] = "UNVERIFIED"
    s = fp.apply_data_gaps(sk, {"outflows_truncated_at_100": True})
    assert not s["_no_data"] and len(s["_data_gaps"]) == 2

def test_shipped_br_skeleton_if_present(monkeypatch):
    p = pathlib.Path("/workspace/br-forensic/skeleton.json")
    if not p.exists():
        return
    monkeypatch.setenv("HF_API_MODE", "live")
    s = fp.apply_data_gaps(json.loads(p.read_text()), None)
    assert s["chain_state"] == "UNKNOWN"
