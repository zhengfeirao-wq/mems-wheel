"""Start one bounded recording through the running monitor, leaving its view open."""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://10.42.0.101:8875")
parser.add_argument("--seconds", type=float, default=45)
parser.add_argument("--output", type=Path, default=Path("reports/press_plot_20260910_run01"))
args = parser.parse_args()
if args.seconds <= 0:
    parser.error("--seconds must be positive")
base = args.url.rstrip("/")
output = args.output
output.mkdir(parents=True, exist_ok=False)
page = urlopen(base, timeout=3).read().decode("utf-8")
token = re.search(r'const token="([^"]+)"', page).group(1)


def get():
    return json.load(urlopen(base + "/api/snapshot", timeout=3))


def post(action):
    return json.load(urlopen(Request(base + "/api/record/" + action,
        method="POST", headers={"X-Tactile-Control": token}), timeout=15))


before = get()
if before["recording"]["active"]:
    raise RuntimeError("An existing user recording is active; will not stop it.")
start = post("start")
print(json.dumps({"started": start, "duration_seconds": args.seconds}), flush=True)
began = time.monotonic()
live = None
try:
    time.sleep(args.seconds)
    live = get()
finally:
    finish = post("stop")
result = {"started": start, "finished": finish, "elapsed_seconds": time.monotonic() - began,
          "live_before_stop": live,
          "press_annotations": "User asked to start; suggested timing is not an observed press log."}
(output / "control.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"finished": finish, "output": str(output)}), flush=True)
