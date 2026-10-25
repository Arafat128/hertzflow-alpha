"""Perseus fix 4: clock timestamps on every pipeline log line, in Asia/Dhaka
(UTC+06, no DST). HF_TS_LOG=0 disables. Also section start/end timing records."""
from __future__ import annotations
import io, os, sys, json, time, threading
from datetime import datetime, timedelta, timezone

DHAKA = timezone(timedelta(hours=6), "+06")


def now_str() -> str:
    return datetime.now(DHAKA).strftime("%Y-%m-%d %H:%M:%S+06")


class _TSStream(io.TextIOBase):
    def __init__(self, inner):
        self._inner = inner
        self._bol = True
        self._lock = threading.Lock()

    def write(self, s):
        if not s:
            return 0
        with self._lock:
            out = []
            for part in s.splitlines(keepends=True):
                if self._bol and part.strip():
                    out.append(f"[{now_str()}] ")
                out.append(part)
                self._bol = part.endswith("\n")
            self._inner.write("".join(out))
        return len(s)

    def flush(self):
        self._inner.flush()

    def __getattr__(self, k):
        return getattr(self._inner, k)


def install_stderr() -> bool:
    if os.environ.get("HF_TS_LOG", "1") == "0" or isinstance(sys.stderr, _TSStream):
        return False
    sys.stderr = _TSStream(sys.stderr)
    return True


class Timeline:
    """Wall-clock section log → .work/timing.json"""
    def __init__(self):
        self.t0 = time.time()
        self.events: list[dict] = []

    def mark(self, section: str, seconds: float | None = None, **extra):
        self.events.append({"section": section, "at": now_str(),
                            "seconds": None if seconds is None else round(seconds, 2), **extra})

    def write(self, path):
        doc = {"tz": "Asia/Dhaka (UTC+06)", "started": datetime.fromtimestamp(self.t0, DHAKA)
               .strftime("%Y-%m-%d %H:%M:%S+06"), "finished": now_str(),
               "total_seconds": round(time.time() - self.t0, 2), "events": self.events}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=1, ensure_ascii=False)
        return doc
