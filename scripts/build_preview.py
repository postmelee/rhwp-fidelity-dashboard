#!/usr/bin/env python3
"""Build the review site from the existing validated numeric ledger."""
import argparse
from pathlib import Path

import pipeline
from core import manifest
from preview_presentation import render_site


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("ledger"))
    parser.add_argument("--out", type=Path, default=Path("preview"))
    args = parser.parse_args()

    corpus = pipeline.ROOT / "corpus"
    folder = args.ledger / "records"
    # Keep JSON export on the same validated path as the production builder.
    pipeline.build(folder, args.out, corpus)
    docs = manifest(corpus, verify=False)["documents"]
    render_site(args.out, pipeline.history(folder, docs), docs)


if __name__ == "__main__":
    main()
