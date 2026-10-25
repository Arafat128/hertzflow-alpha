import io, json, re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "helpers"))
import tslog

def test_prefix_each_line():
    buf = io.StringIO(); s = tslog._TSStream(buf)
    s.write("a\nb"); s.write(" c\n\n")
    lines = buf.getvalue().splitlines()
    assert re.match(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\+06\] a$", lines[0])
    assert lines[1].endswith("] b c") and lines[2] == ""

def test_timeline(tmp_path):
    t = tslog.Timeline(); t.mark("rule_11", 1.234)
    d = t.write(tmp_path / "timing.json")
    assert d["tz"].startswith("Asia/Dhaka") and d["events"][0]["seconds"] == 1.23
    assert json.loads((tmp_path / "timing.json").read_text())["finished"].endswith("+06")
