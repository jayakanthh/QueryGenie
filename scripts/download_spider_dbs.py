#!/usr/bin/env python3
"""
Download the Spider SQLite databases (and dev.json / tables.json) from Hugging Face into
data/spider_full/spider_data/, where the app and the local evaluation look for them.

Source: the Hugging Face dataset HAL-9001/spider-databases (spider_data.zip) — the same
archive the Colab harness (research/colab_eval_tier2.py) uses. Hugging Face is an approved
data source under the department SOP.

    python scripts/download_spider_dbs.py
"""
import os
import zipfile

from huggingface_hub import hf_hub_download

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "data", "spider_full")


def main():
    if os.path.exists(os.path.join(DEST, "spider_data", "dev.json")):
        print("already present:", os.path.join(DEST, "spider_data"))
        return
    z = hf_hub_download("HAL-9001/spider-databases", "spider_data.zip", repo_type="dataset", local_dir=DEST)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(DEST)
    print("extracted to", os.path.join(DEST, "spider_data"))


if __name__ == "__main__":
    main()
