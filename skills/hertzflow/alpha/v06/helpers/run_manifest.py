"""Perseus fix 9: file mtimes get reset on the box, so provenance lives in
<run>/.work/run_manifest.json: UTC+06 write time + sha256 + size of every
output, skill version and git HEAD. `verify()` re-checks hashes later."""
from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path
try:
    from tslog import now_str
except Exception:  # pragma: no cover
    from datetime import datetime, timedelta, timezone
    def now_str():
        return datetime.now(timezone(timedelta(hours=6))).strftime("%Y-%m-%d %H:%M:%S+06")

SKIP_DIRS = {"__pycache__", ".git"}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git_head() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(Path(__file__).parent), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:
        return None


def write(run_dir, extra: dict | None = None) -> Path:
    run_dir = Path(run_dir)
    files = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file() and not (set(p.parts) & SKIP_DIRS) and p.name != "run_manifest.json":
            files[str(p.relative_to(run_dir))] = {"sha256": _sha(p), "bytes": p.stat().st_size}
    try:
        from _version import __version__ as ver
    except Exception:
        ver = None
    doc = {"written": now_str(), "tz": "Asia/Dhaka (UTC+06)", "skill_version": ver,
           "git_head": _git_head(), "files": files, **(extra or {})}
    out = run_dir / ".work" / "run_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def verify(run_dir) -> dict:
    run_dir = Path(run_dir)
    doc = json.loads((run_dir / ".work" / "run_manifest.json").read_text(encoding="utf-8"))
    bad = {}
    for rel, meta in doc["files"].items():
        p = run_dir / rel
        if not p.exists():
            bad[rel] = "missing"
        elif _sha(p) != meta["sha256"]:
            bad[rel] = "changed"
    return bad
