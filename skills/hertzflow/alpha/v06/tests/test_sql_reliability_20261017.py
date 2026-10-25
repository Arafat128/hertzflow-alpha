"""2026-10-17 local patch tests: async routing, retry/permanent, key pool,
stdin, concurrency, BETWEEN guard, UNKNOWN status. Fully mocked — no network.
Run with FAKE keys only (the runner strips real SURF_* env vars)."""
import json, os, sys, threading, time, subprocess, types, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "helpers"))
os.environ.update({"HF_CACHE": "0", "HF_ASYNC_POLL_SECS": "0.01", "HF_BUDGET": "0"})
_ENV_BEFORE = dict(os.environ)
for i in range(4, 12):
    os.environ[f"SURF_API_KEY_{i}"] = f"fake-key-{i}"
os.environ["SURF_API_KEY"] = "fake-stray-override"
import api_gateway as gw
_ORIG_RUN = subprocess.run
_ORIG_REAL = gw._REAL_RUN

gw._random = types.SimpleNamespace(uniform=lambda a, b: 0.0)
gw._backoff = lambda attempt, err: 0.0

JOIN_SQL = "WITH a AS (SELECT 1) SELECT x FROM agent.bsc_transfers t LEFT JOIN a ON 1=1 WHERE block_date >= today() - 7"
PLAIN_SQL = "SELECT \"to\" FROM agent.bsc_transfers WHERE contract_address='0xabc' AND block_date >= today() - 7"


def cp(argv, rc, out):
    return subprocess.CompletedProcess(argv, rc, out, "")


class FakeSurf:
    def __init__(self, script):
        self.script = script  # endpoint -> list of (rc, body) consumed in order
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, argv, **kw):
        with self.lock:
            self.calls.append((list(argv), kw))
            ep = argv[1]
            seq = self.script.get(ep)
            rc, body = seq.pop(0) if len(seq) > 1 else seq[0]
        if callable(body):
            body = body(argv, kw)
        return cp(argv, rc, body if isinstance(body, str) else json.dumps(body))


def job(status, **x):
    d = {"job_id": "11111111-2222-3333-4444-555555555555", "status": status}
    d.update(x)
    return {"data": d, "meta": {"credits_used": 4 if status == "queued" else 0}}


ASYNC_OK = {
    "onchain-sql-job-create": [(0, job("queued"))],
    "onchain-sql-job-get": [(0, job("running")), (0, job("succeeded", row_count=2))],
    "onchain-sql-job-results": [(0, {"data": [{"x": 1}, {"x": 2}], "meta": {"credits_used": 0}})],
}


def run_sql(sql, use_file=False, tmp=None):
    payload = json.dumps({"sql": sql, "max_rows": 100})
    if use_file:
        p = os.path.join(tmp, "q.json")
        open(p, "w").write(payload)
        return subprocess.run(["surf", "onchain-sql", f"@{p}"], capture_output=True, text=True, timeout=40)
    return subprocess.run(["surf", "onchain-sql"], input=payload, capture_output=True, text=True, timeout=40)


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gw.install(None)

    @classmethod
    def tearDownClass(cls):
        # Perseus fork: undo the global gateway install so later test modules
        # see the real subprocess.run (was polluting test_v0713_*).
        subprocess.run = _ORIG_RUN
        gw._REAL_RUN = _ORIG_REAL
        gw._INSTALLED = False
        for k in ["HF_CACHE", "HF_ASYNC_POLL_SECS", "HF_BUDGET", "SURF_API_KEY"] + [f"SURF_API_KEY_{i}" for i in range(4, 12)]:
            if k in _ENV_BEFORE:
                os.environ[k] = _ENV_BEFORE[k]
            else:
                os.environ.pop(k, None)

    def setUp(self):
        gw.S.breaker_tripped = None
        try:
            os.remove(gw._ledger_path())   # fix 1 ledger must not leak between tests
        except OSError:
            pass
        os.environ["SURF_API_KEY"] = "fake-stray-override"
        gw._init_keys()

    def fake(self, script):
        f = FakeSurf({k: list(v) for k, v in script.items()})
        gw._REAL_RUN = f
        return f

    def eps(self, f):
        return [c[0][1] for c in f.calls]

    # ---- routing
    def test_join_goes_straight_to_async(self):
        f = self.fake(ASYNC_OK)
        p = run_sql(JOIN_SQL)
        self.assertEqual(p.returncode, 0)
        d = json.loads(p.stdout)
        self.assertEqual(len(d["data"]), 2)
        self.assertEqual(d["meta"]["credits_used"], 4)
        self.assertEqual(d["meta"]["hf_async"]["reason"], "join")
        self.assertNotIn("onchain-sql", self.eps(f))           # no sync attempt
        create = f.calls[0]
        self.assertIn("--idempotency-key", create[0])
        self.assertTrue(create[0][create[0].index("--idempotency-key") + 1].startswith("hf-"))

    def test_lower_and_long_window_route_async(self):
        self.assertEqual(gw._async_reason("SELECT 1 FROM agent.x WHERE lower(\"to\") IN ('0x1')"), "lower()")
        self.assertTrue(gw._async_reason(
            "SELECT 1 FROM agent.bsc_transfers WHERE block_date BETWEEN '2026-01-01' AND '2026-06-01'").startswith("window"))
        self.assertTrue(gw._async_reason("SELECT 1 FROM agent.t WHERE block_date >= today() - 180").startswith("window"))
        self.assertIsNone(gw._async_reason(PLAIN_SQL))
        self.assertIsNone(gw._async_reason(
            "SELECT 1 FROM agent.t WHERE block_date BETWEEN '2026-09-11' AND '2026-10-10'"))

    def test_sync_requires_async_falls_back(self):
        err = {"error": {"code": "SYNC_QUERY_REQUIRES_ASYNC", "recommended_action": "use_async_job",
                         "retryable": False, "message": "x" * 400}}
        f = self.fake(dict(ASYNC_OK, **{"onchain-sql": [(4, err)]}))
        p = run_sql(PLAIN_SQL)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(self.eps(f).count("onchain-sql"), 1)  # exactly one sync send
        self.assertIn("onchain-sql-job-create", self.eps(f))

    def test_in_flight_reattaches_async(self):
        err = {"error": {"code": "SQL_QUERY_IN_FLIGHT", "message": "an equivalent synchronous query is already running"}}
        f = self.fake(dict(ASYNC_OK, **{"onchain-sql": [(4, err)]}))
        self.assertEqual(run_sql(PLAIN_SQL).returncode, 0)
        self.assertEqual(self.eps(f).count("onchain-sql"), 1)

    def test_rate_limited_backoff_then_ok(self):
        rl = '{\n "error": {"code": "RATE_LIMITED", "message": "too many concurrent queries"}\n}\nWARN: Got 429 Too Many'
        ok = {"data": [{"a": 1}], "meta": {"credits_used": 4}}
        f = self.fake({"onchain-sql": [(4, rl), (4, rl), (0, ok)]})
        p = run_sql(PLAIN_SQL)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(self.eps(f).count("onchain-sql"), 3)

    def test_async_failed_job_is_permanent_error(self):
        f = self.fake({"onchain-sql-job-create": [(0, job("queued"))],
                       "onchain-sql-job-get": [(0, job("failed", error={"code": "QUERY_TIMEOUT", "message": "t"}))]})
        p = run_sql(JOIN_SQL)
        self.assertNotEqual(p.returncode, 0)
        e = json.loads(p.stdout)["error"]
        self.assertEqual(e["code"], "QUERY_TIMEOUT")
        self.assertIs(e["retryable"], False)

    def test_async_timeout_cancels(self):
        old = gw._ASYNC_TIMEOUT
        gw._ASYNC_TIMEOUT = 0
        try:
            f = self.fake({"onchain-sql-job-create": [(0, job("queued"))],
                           "onchain-sql-job-get": [(0, job("running"))],
                           "onchain-sql-job-cancel": [(0, {"data": {}})]})
            p = run_sql(JOIN_SQL)
            self.assertEqual(json.loads(p.stdout)["error"]["code"], "HF_ASYNC_TIMEOUT")
            self.assertIn("onchain-sql-job-cancel", self.eps(f))
        finally:
            gw._ASYNC_TIMEOUT = old

    # ---- stdin / @file
    def test_file_form_sent_via_input_and_devnull_elsewhere(self):
        import tempfile
        ok = {"data": [], "meta": {"credits_used": 4}}
        f = self.fake({"onchain-sql": [(0, ok)], "token-holders": [(0, ok)]})
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(run_sql(PLAIN_SQL, use_file=True, tmp=td).returncode, 0)
        argv, kw = f.calls[0]
        self.assertFalse(any(a.startswith("@") for a in argv))
        self.assertIn("SELECT", kw["input"])
        subprocess.run(["surf", "token-holders", "--address", "0xabc"], capture_output=True, text=True)
        self.assertIs(f.calls[1][1].get("stdin"), subprocess.DEVNULL)

    # ---- key pool
    def test_stray_override_ignored_and_rotation(self):
        self.assertEqual(os.environ["SURF_API_KEY"], "fake-key-4")   # stray override replaced
        pbz = {"error": {"code": "PAID_BALANCE_ZERO", "message": "insufficient credit"}}
        ok = {"data": [{"a": 1}], "meta": {"credits_used": 4}}

        def body(argv, kw):
            return pbz if kw["env"]["SURF_API_KEY"] in ("fake-key-4", "fake-key-5") else ok
        f = self.fake({"onchain-sql": [(0, body)]})
        # rc must be non-zero for PBZ: wrap
        def rc_body(argv, **kw):
            b = body(argv, kw)
            f.calls.append((list(argv), kw))
            return cp(argv, 4 if "error" in b else 0, json.dumps(b))
        gw._REAL_RUN = rc_body
        p = run_sql(PLAIN_SQL)
        self.assertEqual(p.returncode, 0)
        used = [c[1]["env"]["SURF_API_KEY"] for c in f.calls]
        self.assertEqual(used, ["fake-key-4", "fake-key-5", "fake-key-6"])
        self.assertIsNone(gw.S.breaker_tripped)
        self.assertEqual(gw._KEYS.current()[0], "SURF_API_KEY_6")

    def test_all_keys_empty_trips_breaker(self):
        pbz = json.dumps({"error": {"code": "PAID_BALANCE_ZERO", "message": "insufficient credit"}})
        gw._REAL_RUN = lambda argv, **kw: cp(argv, 4, pbz)
        p = run_sql(PLAIN_SQL)
        self.assertNotEqual(p.returncode, 0)
        self.assertTrue(gw._KEYS.exhausted())
        self.assertTrue(gw.S.breaker_tripped)

    # ---- concurrency
    def test_concurrency_cap_3(self):
        state = {"cur": 0, "max": 0}
        lk = threading.Lock()

        def slow(argv, **kw):
            with lk:
                state["cur"] += 1
                state["max"] = max(state["max"], state["cur"])
            time.sleep(0.05)
            with lk:
                state["cur"] -= 1
            return cp(argv, 0, json.dumps({"data": [], "meta": {"credits_used": 1}}))
        gw._REAL_RUN = slow
        ts = [threading.Thread(target=lambda i=i: subprocess.run(
            ["surf", "token-holders", "--address", f"0x{i:040x}"], capture_output=True, text=True))
            for i in range(10)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertLessEqual(state["max"], 3)
        self.assertGreaterEqual(state["max"], 2)


class Wrappers(unittest.TestCase):
    def test_retry_wrapper_full_json_permanent(self):
        import section_a_scope as sa
        body = json.dumps({"$schema": "https://api.asksurf.ai/schemas/UpstreamErrorResponse.json" + "x" * 300,
                           "error": {"async_job_url": "/gateway/v1/onchain/sql/jobs",
                                     "code": "SOME_NEW_CODE", "message": "y" * 300,
                                     "retryable": False}}, indent=2)
        n = {"c": 0}
        real = subprocess.run

        def fake(cmd, **kw):
            n["c"] += 1
            return cp(cmd, 4, body)
        sa.subprocess.run = fake
        try:
            doc, err = sa._run_surf_with_retry(["surf", "onchain-sql"], stdin="{}", max_attempts=4)
        finally:
            sa.subprocess.run = real
        self.assertIsNone(doc)
        self.assertEqual(n["c"], 1)            # was 4 before the patch
        self.assertIn("SOME_NEW_CODE", err)

    def test_parallel_surf_transient_and_between_guard(self):
        import parallel_surf as ps
        self.assertFalse(ps._is_transient_error({"error": {"code": "X", "retryable": False}}))
        self.assertFalse(ps._is_transient_error({"error": {"code": "X", "recommended_action": "use_async_job"}}))
        self.assertTrue(ps._is_transient_error({"error": {"code": "RATE_LIMITED", "message": "busy"}}))
        sql = "SELECT 1 FROM agent.bsc_transfers WHERE block_date BETWEEN '2025-02-15' AND '2025-05-23'"
        g = ps._check_surf_365_day_window(json.dumps({"sql": sql}), "q.json")
        self.assertEqual(g["error"]["code"], "INVALID_REQUEST_GUARD")
        ok = "SELECT 1 FROM agent.bsc_transfers WHERE block_date BETWEEN toDate(today()-30) AND today()"
        self.assertIsNone(ps._check_surf_365_day_window(json.dumps({"sql": ok}), "q.json"))
        self.assertEqual(ps._first_json('{"error":{"code":"RATE_LIMITED"}}\nWARN: Got 429')["error"]["code"], "RATE_LIMITED")

    def test_supply_chain_clamp(self):
        import supply_chain_overhang as sco
        from datetime import date, timedelta
        safe = (date.today() - timedelta(days=364)).isoformat()
        self.assertEqual(sco._clamp_floor("2025-09-30"), max("2025-09-30", safe))
        self.assertEqual(sco._clamp_floor("2020-01-01"), safe)
        self.assertEqual(sco._clamp_floor(date.today().isoformat()), date.today().isoformat())


class Unknown(unittest.TestCase):
    def _run(self, chunk_results):
        import funding_source_attribution as fsa
        real = fsa.parallel_run_chunked
        fsa.parallel_run_chunked = lambda fn, chunks, **k: chunk_results[:len(chunks)] + \
            [{"data": []}] * max(0, len(chunks) - len(chunk_results))
        try:
            ht = fsa.discover_high_throughput_dumpers(
                ca="0x5dbde81fce337ff4bcaaee4ca3466c00aecae274", date_floor="2025-10-17", total_supply=1e9)
            fo = fsa.discover_cex_fanout_hubs(
                ca="0x5dbde81fce337ff4bcaaee4ca3466c00aecae274", date_floor="2025-10-17")
        finally:
            fsa.parallel_run_chunked = real
        return ht, fo

    def test_all_chunks_error_is_unknown(self):
        ht, fo = self._run([{"_error": "SYNC_QUERY_REQUIRES_ASYNC", "data": []}] * 20)
        self.assertEqual(ht["status"], "UNKNOWN")
        self.assertEqual(ht["summary"]["status"], "UNKNOWN")
        self.assertEqual(ht["n_chunk_errors"], ht["n_chunks"])
        self.assertEqual(fo["status"], "UNKNOWN")

    def test_some_chunks_error_is_partial(self):
        ht, fo = self._run([{"_error": "boom", "data": []}])
        if ht["n_chunks"] > 1:
            self.assertEqual(ht["status"], "PARTIAL")
            self.assertEqual(ht["n_chunk_errors"], 1)
            self.assertEqual(fo["status"], "PARTIAL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
