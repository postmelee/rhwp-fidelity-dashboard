#!/usr/bin/env python3
"""Build the review site from the existing validated numeric ledger."""
import argparse
from pathlib import Path

import pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("ledger"))
    parser.add_argument("--out", type=Path, default=Path("preview"))
    args = parser.parse_args()

    corpus = pipeline.ROOT / "corpus"
    folder = args.ledger / "records"
    pipeline.build(folder, args.out, corpus)


if __name__ == "__main__":
    main()
