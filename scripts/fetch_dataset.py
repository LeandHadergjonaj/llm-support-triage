#!/usr/bin/env python3
"""Download the upstream Bitext customer-support dataset into data/raw/.

The raw CSV is 19 MB and is gitignored purely for repo size -- the licence
(CDLA-Sharing-1.0) permits redistribution. See data/README.md.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = (
    "https://huggingface.co/datasets/bitext/"
    "Bitext-customer-support-llm-chatbot-training-dataset/resolve/main/"
    "Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv"
)
DEST = Path(__file__).resolve().parents[1] / "data" / "raw" / "bitext_customer_support.csv"


def main() -> int:
    if DEST.exists():
        print(f"Already present: {DEST} ({DEST.stat().st_size / 1e6:.1f} MB)")
        return 0
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL}")
    urllib.request.urlretrieve(URL, DEST)  # noqa: S310 - fixed https URL
    print(f"Wrote {DEST} ({DEST.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
