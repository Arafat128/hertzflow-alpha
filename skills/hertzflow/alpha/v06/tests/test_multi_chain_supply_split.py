"""test_multi_chain_supply_split.py — 做死 (product spec 2026-07-01, UB).

section_multi_chain must NOT report "单链 完整覆盖" when detect_multichain_split /
supply_chain_overhang found the bulk of supply on another chain. UB trades on BSC
(Alpha) but 87.3% of supply sits on a verified Ethereum contract — the report must
say multi-chain (supply-dominant Ethereum + BSC trading), consistent with the chip's
Ethereum-canonical overhang, not the old "single-chain BSC full coverage"."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "helpers"))
from i18n import set_lang  # noqa: E402
import section_multi_chain as smc  # noqa: E402

set_lang("zh")

_SPLIT = {"split": True, "supply_chain": "ethereum", "supply_chain_label": "Ethereum",
          "supply_pct_of_total": 87.3}


def _rows_text(r):
    return " ".join(x["value"] for x in r["rows"]) + " " + r["gate_note"]


def test_single_chain_unchanged_when_no_split():
    r = smc.run(chain_label="BSC", total_supply=10_000_000_000,
                primary_chain="binance-smart-chain", supply_split={"split": False})
    assert r["single_chain"] is True
    assert r.get("supply_split") is False
    assert "单链" in _rows_text(r)


def test_no_arg_backward_compatible():
    # supply_split defaults to None → single-chain path, no crash.
    r = smc.run(chain_label="BSC", total_supply=10_000_000_000,
                primary_chain="binance-smart-chain")
    assert r["single_chain"] is True


def test_supply_split_reports_multichain_not_single():
    r = smc.run(chain_label="BSC", total_supply=10_000_000_000,
                primary_chain="binance-smart-chain", supply_split=_SPLIT)
    assert r["single_chain"] is False
    assert r.get("supply_split") is True
    txt = _rows_text(r)
    # must name the supply-dominant chain + its % and NOT claim single-chain/full-coverage
    assert "Ethereum" in txt and "87.3" in txt
    assert "多链" in txt
    assert "单链, 无跨链桥" not in txt
    # coverage row must not say bare 完整覆盖 (it says trading-forensic complete + overlay)
    cov = [x["value"] for x in r["rows"] if "覆盖" in x["item"]][0]
    assert "overlay" in cov and "非单链完整覆盖" in cov


def test_split_error_falls_back_to_single_chain():
    # a split dict carrying _error must NOT trigger the multi-chain framing.
    r = smc.run(chain_label="BSC", total_supply=10_000_000_000,
                primary_chain="binance-smart-chain",
                supply_split={"split": True, "_error": "surf down"})
    assert r["single_chain"] is True
