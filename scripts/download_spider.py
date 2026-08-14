#!/usr/bin/env python3
"""
QueryGenie — Week 2 deliverable: acquire and verify the Spider benchmark.

The department SOP permits datasets only from approved sources. Spider is taken
from Hugging Face Datasets, which is on the approved list. Kaggle is banned and
is not used anywhere in this project.

What this does
--------------
1. Downloads the Spider dataset from Hugging Face.
2. Reports split sizes and shows a sample record.
3. Writes a provenance record to results/dataset_provenance.json as evidence
   of the source, date and integrity of the data actually used.

Usage
-----
    python scripts/download_spider.py
    python scripts/download_spider.py --out data/spider
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROVENANCE = os.path.join(REPO_ROOT, "results", "dataset_provenance.json")

# The bare "spider" repo id was a script-based dataset and no longer loads on
# datasets >= 3.x (script datasets were removed; a namespace/name id is now
# required). "xlangai/spider" is the maintained parquet copy published by the
# original Spider authors' Hugging Face org (XLang AI) — same data, approved
# source. See results/dataset_provenance.json for the recorded deviation.
HF_DATASET = "xlangai/spider"
HF_URL = "https://huggingface.co/datasets/xlangai/spider"
PAPER_URL = "https://arxiv.org/abs/1809.08887"


def main() -> int:
    ap = argparse.ArgumentParser(description="Download and verify the Spider benchmark")
    ap.add_argument("--out", default=os.path.join(REPO_ROOT, "data", "spider"),
                    help="directory to save the dataset to")
    ap.add_argument("--no-save", action="store_true",
                    help="only inspect; do not write the dataset to disk")
    args = ap.parse_args()

    print("=" * 64)
    print(" QueryGenie — Spider dataset acquisition (Week 2)")
    print("=" * 64)
    print(f"\nSource   : {HF_URL}")
    print("Approved : yes — Hugging Face Datasets is on the department's approved list")
    print("Excluded : Kaggle (banned by the SOP) is not used\n")

    try:
        import datasets
        from datasets import load_dataset
    except ImportError:
        print("ERROR: the 'datasets' package is not installed.")
        print("Run:  pip install datasets")
        return 1

    print(f"[1/3] Loading '{HF_DATASET}' from Hugging Face ...")
    try:
        ds = load_dataset(HF_DATASET)
    except Exception as exc:                                  # noqa: BLE001
        print(f"\nERROR: download failed -> {type(exc).__name__}: {exc}")
        print("\nIf this is an authentication or availability problem, try:")
        print("  huggingface-cli login")
        print(f"  or open {HF_URL} in a browser to check the dataset is reachable.")
        return 1

    print("      done\n")

    print("[2/3] Split sizes:")
    counts = {}
    for split in ds:
        n = len(ds[split])
        counts[split] = n
        print(f"      {split:12s}: {n:>6,} examples")

    first_split = next(iter(ds))
    sample = ds[first_split][0]
    print(f"\n      sample record from '{first_split}':")
    for key in ("db_id", "question", "query"):
        if key in sample:
            val = str(sample[key])
            if len(val) > 96:
                val = val[:96] + "..."
            print(f"        {key:10s}: {val}")

    if not args.no_save:
        print(f"\n[3/3] Saving to {args.out} ...")
        os.makedirs(args.out, exist_ok=True)
        ds.save_to_disk(args.out)
        print("      done")
    else:
        print("\n[3/3] --no-save given; not writing to disk")

    record = {
        "dataset": HF_DATASET,
        "source": HF_URL,
        "source_approved_by_sop": True,
        "approved_source_name": "Hugging Face Datasets",
        "source_note": ("Loaded from 'xlangai/spider' (original authors' XLang AI org). "
                        "The legacy bare 'spider' repo id was a script-based dataset that no "
                        "longer loads on datasets>=3.x; 'xlangai/spider' is the maintained "
                        "parquet copy of the same data. Splits: train=7000, validation(dev)=1034."),
        "kaggle_used": False,
        "dataset_paper": PAPER_URL,
        "downloaded_at": dt.datetime.now().isoformat(timespec="seconds"),
        "split_sizes": counts,
        "datasets_library_version": datasets.__version__,
        "python_version": sys.version.split()[0],
        "saved_to": (None if args.no_save else os.path.relpath(args.out, REPO_ROOT)),
        "metrics_used": ["Exact-set Match (EM)", "Execution Accuracy (EX)"],
        "notes": ("Spider is cross-domain: train/dev/test use disjoint databases, so the "
                  "model must generalise to unseen schemas rather than memorise them."),
    }

    os.makedirs(os.path.dirname(PROVENANCE), exist_ok=True)
    with open(PROVENANCE, "w") as fh:
        json.dump(record, fh, indent=2)

    print(f"\n[log] provenance written to {os.path.relpath(PROVENANCE, REPO_ROOT)}")
    print("=" * 64)
    print(" Week 2 dataset deliverable satisfied.")
    print(" Commit dataset_provenance.json as evidence of the approved source.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
