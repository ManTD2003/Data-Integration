"""Đo chất lượng trích xuất kỹ năng bằng nhãn có sẵn của nguồn.

itviec và data_jobs tự gắn `skills_given`, độc lập với phần mô tả công việc. Che nhãn
đi, chạy bộ trích xuất trên text rồi so lại với nhãn — đây là *silver standard* theo
kiểu distant supervision, không phải gold do người gán:

- Nhãn của site không đầy đủ (tin đòi Docker nhưng site không tag Docker), nên kỹ năng
  trích được mà không có trong nhãn chưa hẳn sai. Precision đo được vì thế là **chặn
  dưới** của precision thật; recall thì tin cậy hơn.
- Với data_jobs, `requirements_raw` chính là `job_skills` đã nối chuỗi (xem
  `schema_mapping.map_data_jobs`), dùng nó làm đầu vào thì phép đo chỉ đọc lại nhãn.
  Nên nguồn này chỉ đo trên `title`, và con số recall thấp là điều dự kiến.

Nguồn vieclam24h không có nhãn sẵn nên không xuất hiện ở đây; muốn có số cho nó thì
phải gán nhãn tay một mẫu tin.
"""

from __future__ import annotations

import json

from src.common.paths import STAGING
from src.eval.metrics import SetScore
from src.process.extract_skills import (
    MIN_FUZZY_TOKEN_LEN,
    extract_from_source_field,
    extract_from_text,
)
from src.process.skill_dictionary import SkillDictionary, load_or_build

# Trường an toàn để đo, theo từng nguồn: không được chứa chính danh sách nhãn.
EVAL_FIELDS = {
    "itviec": ("title", "requirements_raw", "description"),
    "data_jobs": ("title",),
}


def load_records() -> list[dict]:
    path = STAGING / "records_deduped.jsonl"
    with open(path, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return [r for r in records if r.get("is_canonical", True)]


def _masked(rec: dict, fields: tuple[str, ...]) -> dict:
    return {field: rec.get(field) for field in fields}


def evaluate(records: list[dict], skill_dict: SkillDictionary, aliases: list[str]) -> dict:
    overall = SetScore()
    per_source: dict[str, SetScore] = {}
    per_method: dict[str, list[int]] = {}

    n_records = 0
    for rec in records:
        fields = EVAL_FIELDS.get(rec["source"])
        if fields is None or not rec.get("extra", {}).get("skills_given"):
            continue

        gold = {m["skill_id"] for m in extract_from_source_field(rec, skill_dict)}
        if not gold:
            continue

        matches = extract_from_text(_masked(rec, fields), skill_dict, aliases)
        pred = {m["skill_id"] for m in matches}

        overall.update(gold, pred)
        per_source.setdefault(rec["source"], SetScore()).update(gold, pred)
        for match in matches:
            hit, total = per_method.setdefault(match["method"], [0, 0])
            per_method[match["method"]] = [hit + (match["skill_id"] in gold), total + 1]
        n_records += 1

    return {
        "n_records": n_records,
        "overall": overall.as_dict(),
        "per_source": {source: score.as_dict() for source, score in per_source.items()},
        "per_method": {
            method: {"n": total, "precision": hit / total if total else 0.0}
            for method, (hit, total) in per_method.items()
        },
    }


def run() -> dict:
    records = load_records()
    skill_dict = load_or_build(records)
    aliases = [a for a in skill_dict.alias_index if " " not in a and len(a) >= MIN_FUZZY_TOKEN_LEN]
    return evaluate(records, skill_dict, aliases)
