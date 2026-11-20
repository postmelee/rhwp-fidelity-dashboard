"""Check that public Pages serves the exact site built from the validated ledger."""
from pathlib import Path
import time
import urllib.request

ROOT = Path("site")
BASE = "https://postmelee.github.io/rhwp-fidelity-dashboard/"
paths = ["index.html", "summary.json", "dashboard.css", "dashboard.js"]
paths.extend(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "records").glob("*.json")))
expected = {name: (ROOT / name).read_bytes() for name in paths}

for attempt in range(30):
    try:
        suffix = "?verify=" + str(time.time_ns())
        for name, data in expected.items():
            url_path = "" if name == "index.html" else name
            with urllib.request.urlopen(BASE + url_path + suffix, timeout=15) as response:
                if response.read() != data:
                    raise ValueError(f"public content differs for {name}")
        print(f"Verified public HTML, assets and every numeric record ({len(paths)} files): {BASE}")
        break
    except (OSError, ValueError) as error:
        if attempt == 29:
            raise SystemExit(f"Live Pages verification failed: {error}") from error
        time.sleep(5)
