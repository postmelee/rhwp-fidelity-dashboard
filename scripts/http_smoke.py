"""Exercise the generated page over HTTP without a browser dependency."""
import json
import time
import urllib.request
for attempt in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/index.html", timeout=2) as r:
            page = r.read().decode()
        assert "rhwp fidelity dashboard" in page
        assert "overflow-x:auto" in page
        assert "Canvas2D and Skia against the same Hancom golden" in page
        assert "Last recorded complete:" in page
        assert "Redeployment displays historical results" in page
        with urllib.request.urlopen("http://127.0.0.1:8000/summary.json", timeout=2) as r:
            data = json.load(r)
        assert type(data["target_documents"]) is int and data["target_documents"] >= 0
        assert data["last_complete"] is None
        print("HTTP page smoke passed (no fabricated results)")
        break
    except OSError:
        time.sleep(0.1)
else:
    raise SystemExit("HTTP smoke failed")
