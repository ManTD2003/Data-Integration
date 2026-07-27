from __future__ import annotations

import argparse
import json
from datetime import datetime

from src.common.paths import RAW
from src.ingestion.wrappers.itviec import ItviecWrapper
from src.ingestion.wrappers.vieclam24h import Vieclam24hWrapper

WRAPPERS = {"vieclam24h": Vieclam24hWrapper, "itviec": ItviecWrapper}


def load_queries(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def rec_key(rec: dict):
    return rec.get("id") or rec.get("job_key") or rec.get("slug")


def run(source: str, queries: list[str], max_pages: int) -> str:
    wrapper = WRAPPERS[source](max_pages=max_pages)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = RAW / f"{source}_{stamp}.jsonl"
    seen: set = set()
    kept = 0
    tasks = queries if getattr(wrapper, "query_based", True) else [None]
    try:
        with open(out, "w", encoding="utf-8") as f:
            for task in tasks:
                found = 0
                for rec in wrapper.search(task):
                    key = rec_key(rec)
                    if key in seen:
                        continue
                    seen.add(key)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    kept += 1
                    found += 1
                print(f"  [{task or 'all'}] +{found}")
    finally:
        wrapper.close()
    print(f"Saved {kept} records -> {out}")
    return str(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="vieclam24h", choices=list(WRAPPERS))
    ap.add_argument("--queries", default="config/queries.txt")
    ap.add_argument("--max-pages", type=int, default=5)
    args = ap.parse_args()
    run(args.source, load_queries(args.queries), args.max_pages)


if __name__ == "__main__":
    main()
