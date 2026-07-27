from __future__ import annotations

import argparse
import json
import time
from datetime import datetime

import httpx

from src.common.paths import RAW

ROWS_API = "https://datasets-server.huggingface.co/rows"
PAGE = 100


def fetch_rows(dataset: str, config: str, split: str, limit: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    with httpx.Client(timeout=40.0) as client:
        while offset < limit:
            length = min(PAGE, limit - offset)
            params = {
                "dataset": dataset,
                "config": config,
                "split": split,
                "offset": offset,
                "length": length,
            }
            resp = client.get(ROWS_API, params=params)
            resp.raise_for_status()
            rows = resp.json().get("rows", [])
            if not rows:
                break
            for r in rows:
                out.append(r["row"])
            offset += length
            time.sleep(0.3)
    return out


def run(dataset: str, config: str, split: str, limit: int) -> str:
    rows = fetch_rows(dataset, config, split, limit)
    tag = dataset.split("/")[-1]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RAW / f"{tag}_{stamp}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for i, row in enumerate(rows):
            row["_source"] = tag
            row["_row_id"] = i
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Saved {len(rows)} records -> {out}")
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="lukebarousse/data_jobs")
    ap.add_argument("--config", default="default")
    ap.add_argument("--split", default="train")
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()
    run(args.dataset, args.config, args.split, args.limit)


if __name__ == "__main__":
    main()
