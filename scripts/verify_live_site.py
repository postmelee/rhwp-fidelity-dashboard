"""Verify the actual Pages response, including the exact newly published JSON."""
import json
from pathlib import Path
import time
import urllib.request

expected = json.loads(Path("site/summary.json").read_text())
base = "https://postmelee.github.io/rhwp-fidelity-dashboard/"
for attempt in range(30):
    try:
        suffix = "?verify=" + str(time.time_ns())
        with urllib.request.urlopen(base + "summary.json" + suffix, timeout=15) as response:
            observed = json.load(response)
        with urllib.request.urlopen(base + suffix, timeout=15) as response:
            page = response.read().decode()
        if observed == expected and "rhwp fidelity dashboard" in page and 'id="filter"' in page and "Canvas2D and Skia against the same Hancom golden" in page:
            print("Live Pages HTML and exact summary verified: " + base)
            break
    except (OSError, ValueError):
        pass
    time.sleep(5)
else:
    raise SystemExit("Live Pages response did not match the published artifact")
