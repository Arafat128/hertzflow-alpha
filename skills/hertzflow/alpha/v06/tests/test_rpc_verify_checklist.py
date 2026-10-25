import sys, json, pathlib
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "scripts")); sys.path.insert(0, str(V06 / "helpers"))
import rpc_verify as rv, surf_checklist as sc

CA, SAFE, EOA = "0x" + "1" * 40, "0x" + "2" * 40, "0x" + "3" * 40
def fake(chain, method, params, timeout=8.0):
    if method == "eth_call":
        to, data = params[0]["to"], params[0]["data"]
        if data == "0x313ce567": return "0x" + hex(18)[2:].rjust(64, "0"), "u"
        if data == "0x18160ddd": return hex(10**9 * 10**18), "u"
        if data.startswith("0x70a08231"):
            who = "0x" + data[-40:]
            return hex((100 if who == SAFE else 50) * 10**18), "u"
        if to == SAFE and data == "0xe75235b8": return "0x" + "1".rjust(64, "0"), "u"
        if to == SAFE and data == "0xa0e67e2b":
            return "0x" + "20".rjust(64, "0") + "1".rjust(64, "0") + ("ab" * 20).rjust(64, "0"), "u"
        return "0x", "u"
    if method == "eth_getCode": return ("0x6080" if params[0] == SAFE else "0x"), "u"
    return None, None

def test_verify_and_checklist(tmp_path, monkeypatch):
    monkeypatch.setattr(rv.rp, "call", fake)
    (tmp_path / ".work").mkdir()
    sk = {"meta": {"symbol": "TST", "contract_address": CA, "coingecko_platforms": {"binance-smart-chain": CA},
          "chain_lp_realtime": {"binance-smart-chain": {"top_holders_classified": {"unclassified": {"top": [
              {"addr": SAFE, "balance": 100.0}, {"addr": EOA, "balance": 80.0}]}}}}},
          "_data_gaps": [{"section": "rule_11", "reason": "trace failed"}]}
    (tmp_path / ".work" / "skeleton.json").write_text(json.dumps(sk))
    d = rv.verify(tmp_path, do_mint=False, do_alpha=False)
    st = {(c["check"], c["note"].split(" · ")[0]): c for c in d["checks"]}
    assert st[("holder_balance", SAFE)]["status"] == "MATCH" and "Safe 1-of-1" in st[("holder_balance", SAFE)]["note"]
    assert st[("holder_balance", EOA)]["status"] == "DRIFT"
    assert d["surf_credits"] == 0
    p, n0 = sc.build(tmp_path)
    assert "ARKHAM REQUIRED" in p.read_text()
    (tmp_path / ".work" / "arkham_xcheck.json").write_text(json.dumps({"status": "ok", "truncated": [SAFE],
        "labels": [{"addr": SAFE, "entity": "Bitget", "label": "Hot Wallet"}, {"addr": EOA, "entity": "unlabelled"}],
        "inferences": []}))
    p, n = sc.build(tmp_path)
    t = p.read_text()
    assert "Arkham labels [A] to confirm" in t and "Bitget (Hot Wallet)" in t and "stopped at 100" in t
    assert "Balances moved" in t and "Data gap (rule_11)" in t and "Already verified by free RPC" in t
    assert n == 1 + 1 + 2 + len(sc.OFFCHAIN)
