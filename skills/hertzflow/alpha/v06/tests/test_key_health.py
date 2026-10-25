import subprocess, sys, os, pathlib
V06 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V06 / "helpers"))

def _run(env, *args):
    return subprocess.run([sys.executable, str(V06 / "scripts" / "key_health.py"), *args],
                          capture_output=True, text=True, env=env, timeout=30)

def test_key_health_never_prints_values(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SURF_API_KEY")}
    env.update(HF_KEY_LEDGER=str(tmp_path / "l.json"), SURF_API_KEY_4="secret-AAA", SURF_API_KEY_5="secret-BBB")
    import api_gateway as gw
    os.environ["HF_KEY_LEDGER"] = env["HF_KEY_LEDGER"]
    gw.record_pbz("SURF_API_KEY_4", "secret-AAA")
    p = _run(env)
    assert p.returncode == 0 and "secret-" not in p.stdout + p.stderr
    assert "known-empty" in p.stdout
    gw.record_pbz("SURF_API_KEY_5", "secret-BBB")
    assert _run(env).returncode == 3
    assert _run(env, "--reset", "all").returncode == 0

def test_no_keys(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SURF_API_KEY")}
    env["HF_KEY_LEDGER"] = str(tmp_path / "l.json")
    assert _run(env).returncode == 4
