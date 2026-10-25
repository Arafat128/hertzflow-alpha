"""Perseus fork: health-ordered public RPC pool (free; 0 Surf credits).

urls(chain)  -> endpoints for 'bsc' / 56 / '56', best-first by recorded health
call(chain, method, params) -> (result, url) trying each endpoint in order;
               records ok/fail + latency to the health file. Returns (None, None)
               when all fail. JSON-RPC errors count as failures.
HF_RPC_HEALTH overrides the health path; HF_RPC_OFFLINE=1 disables network (tests).
"""
from __future__ import annotations
import json, os, time, urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_YAML = _HERE.parent / "rpcs.yaml"
_DEFAULT = {  # used only if rpcs.yaml / PyYAML unavailable
    "ethereum": (1, ["https://ethereum.publicnode.com", "https://eth.llamarpc.com"]),
    "bsc": (56, ["https://bsc-dataseed.binance.org", "https://bsc.publicnode.com"]),
    "polygon": (137, ["https://polygon-rpc.com", "https://polygon.publicnode.com"]),
    "base": (8453, ["https://mainnet.base.org", "https://base.publicnode.com"]),
    "arbitrum": (42161, ["https://arb1.arbitrum.io/rpc", "https://arbitrum.publicnode.com"]),
    "optimism": (10, ["https://mainnet.optimism.io", "https://optimism.publicnode.com"]),
    "avalanche": (43114, ["https://api.avax.network/ext/bc/C/rpc", "https://avalanche.publicnode.com"]),
    "solana": ("solana", ["https://api.mainnet-beta.solana.com"]),
}
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            import yaml
            doc = yaml.safe_load(_YAML.read_text())["chains"]
            _cache = {k: (v["id"], list(v["urls"])) for k, v in doc.items()}
        except Exception:
            _cache = dict(_DEFAULT)
    return _cache


def _key(chain) -> str | None:
    c = str(chain).lower() if chain is not None else "bsc"
    chains = _load()
    if c in chains:
        return c
    for k, (cid, _) in chains.items():
        if str(cid) == c:
            return k
    return {"eth": "ethereum", "bnb": "bsc", "arb": "arbitrum", "op": "optimism",
            "matic": "polygon", "avax": "avalanche", "sol": "solana"}.get(c)


def _health_path() -> Path:
    return Path(os.environ.get("HF_RPC_HEALTH", "/workspace/hertzflow-cache/rpc_health.json"))


def _health() -> dict:
    try:
        return json.loads(_health_path().read_text())
    except Exception:
        return {}


def _record(url: str, ok: bool, ms: float) -> None:
    h = _health()
    e = h.setdefault(url, {"ok": 0, "fail": 0, "ms": None, "ts": 0})
    e["ok" if ok else "fail"] += 1
    if ok:
        e["ms"] = round(ms if e["ms"] is None else 0.7 * e["ms"] + 0.3 * ms, 1)
    e["ts"] = int(time.time())
    e["last"] = "ok" if ok else "fail"
    try:
        p = _health_path(); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(h, indent=1)); tmp.replace(p)
    except OSError:
        pass


def _score(url: str, h: dict, idx: int) -> tuple:
    e = h.get(url)
    if not e:
        return (1, 0.0, idx)                     # unknown: keep yaml order, after healthy
    tot = e["ok"] + e["fail"]
    rate = e["ok"] / tot if tot else 0.0
    recent_fail = e.get("last") == "fail" and time.time() - e.get("ts", 0) < 600
    return (2 if recent_fail else 0 if rate >= 0.5 else 1, -rate, (e["ms"] or 9e9), idx)


def urls(chain) -> list[str]:
    k = _key(chain)
    if not k:
        return []
    lst = _load()[k][1]
    h = _health()
    return sorted(lst, key=lambda u: _score(u, h, lst.index(u)))


def call(chain, method: str, params: list, timeout: float = 8.0):
    if os.environ.get("HF_RPC_OFFLINE") == "1":
        return None, None
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    for u in urls(chain):
        t0 = time.time()
        try:
            req = urllib.request.Request(u, data=body, headers={"Content-Type": "application/json",
                                                                 "User-Agent": "hertzflow-perseus/rpc"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                doc = json.loads(r.read().decode("utf-8", "replace"))
            if "result" in doc and doc.get("error") is None:
                _record(u, True, (time.time() - t0) * 1000)
                return doc["result"], u
        except Exception:
            pass
        _record(u, False, 0)
    return None, None
