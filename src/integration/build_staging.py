from __future__ import annotations

import json
import sys

from src.common.paths import RAW, STAGING
from src.integration.schema_mapping import MAPPERS


def raw_key(raw: dict) -> str:
    """Khoá định danh bản ghi thô trong phạm vi một nguồn."""
    ident = raw.get("id") or raw.get("job_key") or raw.get("slug") or raw.get("_row_id")
    return f"{raw.get('_source')}:{ident}"


def iter_raw():
    """Duyệt data/raw theo thứ tự tên file (tên có timestamp nên là thứ tự thời gian).

    Mỗi lượt cào sinh một file mới, các lượt cào chồng lấn nhau rất nhiều; nếu nạp
    tất cả thì cùng một tin vào staging nhiều lần và mọi số đếm theo nguồn đều sai.
    Bản ghi trùng khoá thì bản của file mới hơn thắng.
    """
    latest: dict[str, dict] = {}
    for path in sorted(RAW.glob("*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    raw = json.loads(line)
                    latest[raw_key(raw)] = raw
    return latest.values()


def run() -> str:
    out = STAGING / "records.jsonl"
    stats: dict[str, int] = {}
    errors: dict[str, list[str]] = {}
    with open(out, "w", encoding="utf-8") as f:
        for raw in iter_raw():
            source = raw.get("_source")
            mapper = MAPPERS.get(source)
            if mapper is None:
                continue
            try:
                record = mapper(raw)
            except Exception as exc:
                errors.setdefault(source, []).append(f"{raw_key(raw)}: {type(exc).__name__} {exc}")
                continue
            f.write(record.model_dump_json() + "\n")
            stats[source] = stats.get(source, 0) + 1

    print("Mapped records per source:", stats)
    for source, messages in errors.items():
        print(f"Lỗi ánh xạ {source}: {len(messages)} bản ghi", file=sys.stderr)
        for message in messages[:5]:
            print(f"  {message}", file=sys.stderr)
    print(f"Staging -> {out}")
    return str(out)


if __name__ == "__main__":
    run()
