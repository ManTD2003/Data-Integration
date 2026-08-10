"""Đo công cụ tìm kiếm: xếp hạng kỹ năng theo truy vấn người dùng, và tính đúng của
việc mở rộng theo phân cấp.

Tập truy vấn `data/eval/queries.jsonl` do người soạn: mỗi dòng là chuỗi người dùng gõ
và skill_id mà họ muốn tìm (viết tắt, sai chính tả, tiếng Việt có/không dấu, tên nhóm
tổng quát). Kỳ vọng được viết theo ý người dùng, không phải theo kết quả hệ thống trả
về, nên chỉ số đo được là chất lượng xếp hạng thật.

Phần mở rộng phân cấp không dùng nhãn: nó dựng lại tập hậu duệ từ `parent_skill_id`
bằng Python rồi so với `skill_closure`, tức hai đường tính độc lập kiểm nhau.
"""

from __future__ import annotations

import json

import duckdb

from src.api.queries import expand_skill_ids, search_skills
from src.common.paths import EVAL
from src.eval.metrics import mean, reciprocal_rank

QUERIES_PATH = EVAL / "queries.jsonl"
TOP_K = 10


def load_queries(path=QUERIES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate_skill_search(con: duckdb.DuckDBPyConnection, queries: list[dict], top_k: int = TOP_K) -> dict:
    ranks: list[float] = []
    hits_at_1 = 0
    misses: list[dict] = []
    by_kind: dict[str, list[float]] = {}

    for case in queries:
        ranked = [row["skill_id"] for row in search_skills(con, case["q"], limit=top_k)]
        rr = reciprocal_rank(ranked, case["expect_skill"])
        ranks.append(rr)
        by_kind.setdefault(case.get("kind", "khác"), []).append(rr)
        if ranked[:1] == [case["expect_skill"]]:
            hits_at_1 += 1
        elif rr == 0.0:
            misses.append({"q": case["q"], "expect": case["expect_skill"], "got": ranked[:3]})

    return {
        "n": len(queries),
        "p_at_1": hits_at_1 / len(queries) if queries else 0.0,
        "mrr": mean(ranks),
        "not_found": len(misses),
        "misses": misses,
        "per_kind": {kind: {"n": len(values), "mrr": mean(values)} for kind, values in sorted(by_kind.items())},
    }


def _descendants_from_parents(con: duckdb.DuckDBPyConnection) -> dict[str, set[str]]:
    rows = con.execute("SELECT skill_id, parent_skill_id FROM skills").fetchall()
    children: dict[str, list[str]] = {}
    for skill_id, parent_id in rows:
        if parent_id:
            children.setdefault(parent_id, []).append(skill_id)

    descendants: dict[str, set[str]] = {}
    for skill_id, _ in rows:
        found = {skill_id}
        stack = [skill_id]
        while stack:
            current = stack.pop()
            for child in children.get(current, []):
                if child not in found:
                    found.add(child)
                    stack.append(child)
        descendants[skill_id] = found
    return descendants


def check_expansion(con: duckdb.DuckDBPyConnection) -> dict:
    expected = _descendants_from_parents(con)
    mismatch = []
    for skill_id, want in expected.items():
        got = set(expand_skill_ids(con, skill_id))
        if got != want:
            mismatch.append({"skill_id": skill_id, "missing": sorted(want - got)[:3]})

    with_children = sum(1 for ids in expected.values() if len(ids) > 1)
    return {"n_skills": len(expected), "n_ancestors": with_children, "mismatch": mismatch}


def run(con: duckdb.DuckDBPyConnection) -> dict:
    return {
        "skill_search": evaluate_skill_search(con, load_queries()),
        "expansion": check_expansion(con),
    }
