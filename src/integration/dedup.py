from __future__ import annotations

import json
from collections import defaultdict

from rapidfuzz import fuzz

from src.common.paths import STAGING
from src.common.schema import norm_text

TITLE_SIM = 92
COMPANY_SIM = 88


def blocking_key(rec: dict) -> str:
    company = norm_text(rec.get("company"))
    if company:
        return company[:12]
    return norm_text(rec.get("title"))[:8]


def is_duplicate(a: dict, b: dict) -> bool:
    if a["source"] != b["source"]:
        return False
    title_sim = fuzz.token_sort_ratio(norm_text(a["title"]), norm_text(b["title"]))
    if title_sim < TITLE_SIM:
        return False
    comp_sim = fuzz.token_sort_ratio(norm_text(a.get("company")), norm_text(b.get("company")))
    return comp_sim >= COMPANY_SIM


def assign_groups(records: list[dict]) -> None:
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(records):
        blocks[blocking_key(rec)].append(i)

    parent = list(range(len(records)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        parent[find(x)] = find(y)

    for idxs in blocks.values():
        for pos, i in enumerate(idxs):
            for j in idxs[pos + 1 :]:
                if is_duplicate(records[i], records[j]):
                    union(i, j)

    for i, rec in enumerate(records):
        rec["dup_group_id"] = find(i)

    seen: set[int] = set()
    for rec in records:
        gid = rec["dup_group_id"]
        rec["is_canonical"] = gid not in seen
        seen.add(gid)


def run() -> str:
    src = STAGING / "records.jsonl"
    records = [json.loads(line) for line in open(src, encoding="utf-8")]
    assign_groups(records)

    out = STAGING / "records_deduped.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    groups = {r["dup_group_id"] for r in records}
    canonical = sum(1 for r in records if r["is_canonical"])
    print(f"Records: {len(records)} | groups: {len(groups)} | duplicates removed: {len(records) - canonical}")
    print(f"Deduped staging -> {out}")
    return str(out)


if __name__ == "__main__":
    run()
