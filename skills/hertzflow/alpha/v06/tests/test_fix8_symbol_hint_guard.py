import subprocess, sys, pathlib
V06 = pathlib.Path(__file__).resolve().parents[1]

def test_symbol_hint_refused():
    p = subprocess.run([sys.executable, str(V06 / "forensic_pipeline.py"), "0x" + "a" * 40,
                        "--symbol-hint", "BTW", "--dry-run"], capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "disabled in the Perseus fork" in p.stderr
