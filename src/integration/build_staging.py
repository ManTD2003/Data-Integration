from __future__ import annotations

import json

from src.common.paths import RAW, STAGING
from src.integration.schema_mapping import MAPPERS


def iter_raw():
    for path in sorted(RAW.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)


def run() -> str:
    out = STAGING / "records.jsonl"
    stats: dict[str, int] = {}
    errors = 0
    with open(out, "w", encoding="utf-8") as f:
        for raw in iter_raw():
            source = raw.get("_source")
            mapper = MAPPERS.get(source)
            if mapper is None:
                continue
            try:
                record = mapper(raw)
            except Exception:
                errors += 1
                continue
            f.write(record.model_dump_json() + "\n")
            stats[source] = stats.get(source, 0) + 1
    print("Mapped records per source:", stats, "| errors:", errors)
    print(f"Staging -> {out}")
    return str(out)


if __name__ == "__main__":
    run()
