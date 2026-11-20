"""Presentation of validated immutable records; never combines separate attempts."""
LABELS = {"native": "Native Skia", "wasm": "WASM Canvas2D"}
def number(value):
    return "unavailable" if value is None else f"{value:.5f}".rstrip("0").rstrip(".")

def paired_pages(record, docs):
    """Pair only complete, count-matched pages within the SAME validated run."""
    backends = record["measurement"]["backends"]
    maps = {b: {d["id"]: d for d in backends[b]["documents"]} for b in LABELS}
    rows = []
    for doc in docs:
        pair = [maps[b].get(doc["id"]) for b in ("wasm", "native")]
        valid = all(d and d["status"] == "complete" and
                    d["pdf_pages"] == doc["pages"] == d["rendered_pages"] for d in pair)
        values = [{s["page"]: s["raw"] for s in d["scores"]} if d else {} for d in pair]
        for page in range(1, doc["pages"] + 1):
            comparable = valid and all(page in v for v in values)
            w, n = (values[0][page], values[1][page]) if comparable else (None, None)
            rows.append((doc["id"], page, w, n, None if w is None else n-w))
    return rows
