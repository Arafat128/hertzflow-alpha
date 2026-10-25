#!/usr/bin/env python3
"""Perseus fork: free on-chain re-verification of a finished run (0 Surf credits).

  rpc_verify.py RUN_DIR [--holders 10] [--no-mint] [--no-alpha]

Reads RUN_DIR/.work/skeleton.json and checks, per EVM chain the token is on:
  decimals(), totalSupply(), top-holder balanceOf (drift vs skeleton), whether
  each holder is a contract and, if it answers getThreshold/getOwners, a Safe;
  LP pool balance; contract creation (mint) day by archive getCode bisection;
  Alpha listing date against the free Binance Alpha token list.
Writes RUN_DIR/.work/rpc_verify.json. Status per check:
  MATCH · DRIFT (live value moved, >tol) · MISMATCH · INFO · UNVERIFIED (RPC failed).
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import rpc_pool as rp

DHAKA = timezone(timedelta(hours=6))
ALPHA = "https://www.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/cex/alpha/all/token/list"
CG2CHAIN = {"binance-smart-chain": "bsc", "ethereum": "ethereum", "base": "base", "arbitrum-one": "arbitrum",
            "polygon-pos": "polygon", "optimistic-ethereum": "optimism", "avalanche": "avalanche"}


def _call(chain, to, data, block="latest"):
    r, _ = rp.call(chain, "eth_call", [{"to": to, "data": data}, block])
    return r if isinstance(r, str) and r.startswith("0x") else None


def _uint(h):
    return int(h, 16) if h and h != "0x" else None


def _addr_arr(h):
    try:
        b = h[2:]; n = int(b[64:128], 16)
        return ["0x" + b[128 + 64 * i + 24:128 + 64 * (i + 1)] for i in range(n)]
    except Exception:
        return None


def _pad(a):
    return a.lower().replace("0x", "").rjust(64, "0")


def mint_day(chain, ca):
    """Bisect the first block where `ca` has code (needs an archive-capable RPC)."""
    hi = _uint(rp.call(chain, "eth_blockNumber", [])[0] or "0x0")
    if not hi:
        return None, "no blockNumber"
    code0, _ = rp.call(chain, "eth_getCode", [ca, hex(1)])
    if code0 is None:
        return None, "RPC has no archive state"
    lo = 0
    for _ in range(40):
        if hi - lo <= 1:
            break
        mid = (lo + hi) // 2
        c, _ = rp.call(chain, "eth_getCode", [ca, hex(mid)])
        if c is None:
            return None, f"archive call failed at block {mid}"
        if c not in ("0x", "0x0"):
            hi = mid
        else:
            lo = mid
    b, _ = rp.call(chain, "eth_getBlockByNumber", [hex(hi), False])
    if not b:
        return None, "block lookup failed"
    return datetime.fromtimestamp(int(b["timestamp"], 16), timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), f"block {hi}"


def verify(run: Path, n_holders=10, do_mint=True, do_alpha=True, tol=0.02) -> dict:
    sk = json.loads((run / ".work" / "skeleton.json").read_text())
    meta = sk.get("meta", {})
    plats = meta.get("coingecko_platforms") or {"binance-smart-chain": meta.get("contract_address")}
    checks = []

    def add(check, chain, expected, rpc_val, status, note=""):
        checks.append({"check": check, "chain": chain, "skeleton": expected, "rpc": rpc_val, "status": status, "note": note})

    sk_dec = meta.get("decimals")
    for cg, ca in plats.items():
        chain = CG2CHAIN.get(cg)
        if not chain or not ca:
            add("chain", cg, ca, None, "UNVERIFIED", "non-EVM or unmapped chain"); continue
        dec = _uint(_call(chain, ca, "0x313ce567"))
        add("decimals", chain, sk_dec, dec, "UNVERIFIED" if dec is None else
            ("MATCH" if sk_dec in (None, dec) else "MISMATCH"))
        d = dec if dec is not None else 18
        ts = _uint(_call(chain, ca, "0x18160ddd"))
        add("totalSupply", chain, None, None if ts is None else ts / 10 ** d, "INFO" if ts is not None else "UNVERIFIED",
            "per-chain supply (OFT/bridged tokens differ from global total)")
        lp = (meta.get("chain_lp_realtime") or {}).get(cg) or {}
        if lp.get("top_pool_addr"):
            b = _uint(_call(chain, ca, "0x70a08231" + _pad(lp["top_pool_addr"])))
            add("lp_pool_balance", chain, lp.get("top_pool_balance"), None if b is None else b / 10 ** d,
                "UNVERIFIED" if b is None else "INFO", lp["top_pool_addr"])
        tops = ((lp.get("top_holders_classified") or {}).get("unclassified") or {}).get("top") or []
        for h in tops[:n_holders]:
            a = h["addr"]
            b = _uint(_call(chain, ca, "0x70a08231" + _pad(a)))
            exp = h.get("balance")
            if b is None:
                st = "UNVERIFIED"; live = None
            else:
                live = b / 10 ** d
                st = "MATCH" if exp and abs(live - exp) <= tol * max(exp, 1) else ("DRIFT" if exp else "INFO")
            code, _ = rp.call(chain, "eth_getCode", [a, "latest"])
            kind = None if code is None else ("EOA" if code in ("0x", "0x0") else "contract")
            note = kind or "code?"
            if kind == "contract":
                thr = _uint(_call(chain, a, "0xe75235b8"))
                own = _addr_arr(_call(chain, a, "0xa0e67e2b") or "")
                if thr and own:
                    note = f"Safe {thr}-of-{len(own)} owners {','.join(o[:6] + '…' + o[-4:] for o in own)}"
            add("holder_balance", chain, exp, live, st, f"{a} · {note}")
        if do_mint:
            day, why = mint_day(chain, ca)
            add("mint_time", chain, None, day, "INFO" if day else "UNVERIFIED", why)
    if do_alpha:
        try:
            req = urllib.request.Request(ALPHA, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                lst = json.loads(r.read()).get("data") or []
            ca0 = (meta.get("contract_address") or "").lower()
            e = next((x for x in lst if (x.get("contractAddress") or "").lower() == ca0), None)
            if e and e.get("listingTime"):
                day = datetime.fromtimestamp(int(e["listingTime"]) / 1000, timezone.utc).strftime("%Y-%m-%d")
                add("alpha_listing_date", "binance-alpha", meta.get("alpha_listing_date_utc"), day,
                    "MATCH" if day == meta.get("alpha_listing_date_utc") else "MISMATCH")
                if e.get("decimals") is not None:
                    add("alpha_api_decimals", "binance-alpha", sk_dec, int(e["decimals"]), "INFO")
            else:
                add("alpha_listing_date", "binance-alpha", meta.get("alpha_listing_date_utc"), None, "UNVERIFIED", "CA not in Alpha list")
        except Exception as ex:
            add("alpha_listing_date", "binance-alpha", meta.get("alpha_listing_date_utc"), None, "UNVERIFIED", type(ex).__name__)
    summ = {}
    for c in checks:
        summ[c["status"]] = summ.get(c["status"], 0) + 1
    doc = {"written": datetime.now(DHAKA).strftime("%Y-%m-%d %H:%M:%S+06"), "ca": meta.get("contract_address"),
           "symbol": meta.get("symbol"), "surf_credits": 0, "summary": summ, "checks": checks}
    out = run / ".work" / "rpc_verify.json"
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir"); ap.add_argument("--holders", type=int, default=10)
    ap.add_argument("--no-mint", action="store_true"); ap.add_argument("--no-alpha", action="store_true")
    a = ap.parse_args()
    d = verify(Path(a.run_dir), a.holders, not a.no_mint, not a.no_alpha)
    print(json.dumps(d["summary"]), "→", Path(a.run_dir) / ".work" / "rpc_verify.json")


if __name__ == "__main__":
    main()
