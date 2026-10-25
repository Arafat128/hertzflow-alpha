"""Perseus fork safety net: tests must never reach a paid Surf/Arkham call.
At collection time (before any test module sets its own fake keys) real keys are
removed and a fake `surf` that exits 99 shadows the real CLI on PATH."""
import os, stat, tempfile

for _k in list(os.environ):
    if _k.startswith(("SURF_API_KEY", "ARKHAM")):
        del os.environ[_k]
os.environ["BINANCE_ALPHA_NO_AUTO_UPDATE"] = "1"
_d = tempfile.mkdtemp(prefix="hf-fakebin-")
_f = os.path.join(_d, "surf")
with open(_f, "w") as fh:
    fh.write('#!/bin/sh\necho \'{"error":{"code":"TEST_BLOCKED","message":"real surf blocked in tests"}}\'\nexit 99\n')
os.chmod(_f, os.stat(_f).st_mode | stat.S_IEXEC)
os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")

import pytest

# Known upstream failures (present at ffcf579/baseline), tracked in CHANGELOG "Open".
_KNOWN_XFAIL = {
    "test_zh_json_term_discipline_派发_vs_分发":
        "upstream zh.json copy drift (v1.2.16 multi_chain strings use 派发); zh only, EN Desk path unaffected",
}

def pytest_collection_modifyitems(config, items):
    for it in items:
        r = _KNOWN_XFAIL.get(it.name)
        if r:
            it.add_marker(pytest.mark.xfail(reason=r, strict=False))
