"""Reproduce the paired historical page table from PR #9024's published evidence."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from urllib.request import urlopen

REV = "39a3774de60c81a3b803d158c044ddc195733eb6"
FOLDER = "mydocs/pr/assets/issue8946/stage10-20261114/"
RAW = f"https://raw.githubusercontent.com/edwardkim/rhwp/{REV}/{FOLDER}"


def fetch(name):
    with urlopen(RAW + name, timeout=90) as response:
        return response.read()


def tsv_records(value):
    if isinstance(value, dict):
        if "tsv_sha256" in value and "tsv" in value:
            yield value
        else:
            for child in value.values():
                yield from tsv_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from tsv_records(child)


def read_pages(name, backend, evidence):
    data = fetch("original/head/" + name)
    digest = hashlib.sha256(data).hexdigest()
    matches = [row for row in evidence if row["tsv_sha256"] == digest
               and Path(row["tsv"]).name == name
               and row["provenance"]["raster_backend"] == backend
               and row["provenance"]["comparison_profile"] == "print"]
    if not matches:
        raise ValueError(f"Missing Print evidence for {name}")
    inputs = {(row["provenance"]["hwp"]["sha256"], row["provenance"]["pdf"]["sha256"])
              for row in matches}
    if len(inputs) != 1:
        raise ValueError(f"Ambiguous input pair for {name}")
    pages = {}
    for row in csv.DictReader(io.StringIO(data.decode()), delimiter="\t"):
        page = int(row["page"])
        score = float(row["silhouette_raw_match_percent"])
        if page in pages or not 0 <= score <= 100:
            raise ValueError(f"Invalid score or duplicate page in {name}")
        pages[page] = score
    if set(pages) != set(range(1, 764)):
        raise ValueError(f"Incomplete page scope in {name}")
    return inputs.pop(), pages


def main():
    evidence = list(tsv_records(json.loads(fetch("visual-provenance.json"))))
    a, native = read_pages("hwpx-native.tsv", "native-skia", evidence)
    b, wasm = read_pages("hwpx-wasm.tsv", "wasm-canvas2d", evidence)
    if a != b:
        raise ValueError("Different source or reference PDF")
    expected = [[p, native[p], wasm[p]] for p in sorted(native)]
    if json.loads(Path(sys.argv[1]).read_text()) != expected:
        raise ValueError("Dashboard page rows differ from verified TSVs")
    print(f"Verified {len(expected)} paired pages and both TSV hashes at {REV}")


if __name__ == "__main__":
    main()
