"""Trích xuất kỹ năng từ job record đã chuẩn hoá + khử trùng lặp.

Hai nguồn (itviec, data_jobs) đã có `extra.skills_given` do site tự gắn nhãn ->
dùng thẳng, chỉ cần chuẩn hoá về skill_id trong từ điển (method=source_provided).

Nguồn còn lại (vieclam24h) không có nhãn sẵn -> áp gazetteer trên
title/requirements_raw/description: khớp chính xác theo n-gram (method=exact_match),
sau đó khớp mờ bằng rapidfuzz cho các từ đơn chưa khớp (method=fuzzy_match), để
bắt biến thể viết tắt/gõ sai như trong slide 4_matching_mapping.
"""

from __future__ import annotations

import json
import re

from rapidfuzz import fuzz, process

from src.common.paths import STAGING
from src.process.skill_dictionary import SkillDictionary, _fold, load_or_build

MAX_NGRAM = 4
FUZZY_SCORE_CUTOFF = 92
MIN_FUZZY_TOKEN_LEN = 5

OUTPUT_PATH = STAGING / "job_skills.jsonl"

# \w+ thuần tách rời "C++"/"C#"/".NET" thành ký tự đơn "C" (gây khớp nhầm skill "C"
# ở mọi chỗ có C++/C#). Token này giữ nguyên các tên công nghệ có nối +/#/.
TOKEN_RE = re.compile(r"\.?\w(?:\w|[+#.](?=\w))*[+#]*", re.UNICODE)


def _record_text(rec: dict) -> str:
    parts = [rec.get("title"), rec.get("requirements_raw"), rec.get("description")]
    return " ".join(p for p in parts if p)


def _context(text: str, start: int, end: int, window: int = 30) -> str:
    lo, hi = max(0, start - window), min(len(text), end + window)
    snippet = text[lo:hi].strip()
    return snippet


def _iter_token_spans(text: str):
    return list(TOKEN_RE.finditer(text))


def _match_exact(text: str, skill_dict: SkillDictionary) -> dict[str, dict]:
    """Trả về skill_id -> match info, giữ khớp dài nhất (nhiều từ nhất) khi trùng."""
    tokens = _iter_token_spans(text)
    found: dict[str, dict] = {}
    for size in range(MAX_NGRAM, 0, -1):
        for i in range(len(tokens) - size + 1):
            start, end = tokens[i].start(), tokens[i + size - 1].end()
            phrase = text[start:end]
            skill = skill_dict.lookup(phrase)
            if skill is None:
                continue
            skill_id = skill["skill_id"]
            if skill_id in found:
                continue
            found[skill_id] = {
                "skill": skill,
                "score": 100,
                "evidence": _context(text, start, end),
                "matched_tokens": set(range(i, i + size)),
            }
    return found


def _match_fuzzy(text: str, skill_dict: SkillDictionary, single_word_aliases: list[str], already: dict) -> dict[str, dict]:
    covered_tokens: set[int] = set()
    for info in already.values():
        covered_tokens |= info["matched_tokens"]

    found: dict[str, dict] = {}
    for idx, tok in enumerate(_iter_token_spans(text)):
        if idx in covered_tokens:
            continue
        word = text[tok.start() : tok.end()]
        if len(word) < MIN_FUZZY_TOKEN_LEN or word.isdigit():
            continue
        match = process.extractOne(
            _fold(word), single_word_aliases, scorer=fuzz.ratio, score_cutoff=FUZZY_SCORE_CUTOFF
        )
        if match is None:
            continue
        alias, score, _ = match
        skill = skill_dict.lookup(alias)
        if skill is None or skill["skill_id"] in already or skill["skill_id"] in found:
            continue
        found[skill["skill_id"]] = {
            "skill": skill,
            "score": round(score, 1),
            "evidence": _context(text, tok.start(), tok.end()),
        }
    return found


def extract_from_source_field(rec: dict, skill_dict: SkillDictionary) -> list[dict]:
    matches = []
    for raw_skill in rec.get("extra", {}).get("skills_given") or []:
        skill = skill_dict.lookup(raw_skill)
        if skill is None:
            continue
        matches.append(
            {
                "skill_id": skill["skill_id"],
                "canonical_name": skill["canonical_name"],
                "skill_type": skill["skill_type"],
                "method": "source_provided",
                "score": 100,
                "evidence": raw_skill,
            }
        )
    return matches


def extract_from_text(rec: dict, skill_dict: SkillDictionary, single_word_aliases: list[str]) -> list[dict]:
    text = _record_text(rec)
    if not text:
        return []

    exact = _match_exact(text, skill_dict)
    fuzzy = _match_fuzzy(text, skill_dict, single_word_aliases, exact)

    matches = []
    for skill_id, info in {**exact, **fuzzy}.items():
        method = "exact_match" if skill_id in exact else "fuzzy_match"
        matches.append(
            {
                "skill_id": skill_id,
                "canonical_name": info["skill"]["canonical_name"],
                "skill_type": info["skill"]["skill_type"],
                "method": method,
                "score": info["score"],
                "evidence": info["evidence"],
            }
        )
    return matches


def extract_skills(rec: dict, skill_dict: SkillDictionary, single_word_aliases: list[str]) -> list[dict]:
    if rec.get("extra", {}).get("skills_given"):
        return extract_from_source_field(rec, skill_dict)
    return extract_from_text(rec, skill_dict, single_word_aliases)


def run() -> str:
    records_path = STAGING / "records_deduped.jsonl"
    records = [json.loads(line) for line in open(records_path, encoding="utf-8")]
    canonical = [r for r in records if r.get("is_canonical", True)]

    skill_dict = load_or_build(records)
    single_word_aliases = [a for a in skill_dict.alias_index if " " not in a and len(a) >= MIN_FUZZY_TOKEN_LEN]

    method_counts: dict[str, int] = {}
    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for rec in canonical:
            record_id = f"{rec['source']}:{rec['source_id']}"
            for match in extract_skills(rec, skill_dict, single_word_aliases):
                match["record_id"] = record_id
                match["source"] = rec["source"]
                out.write(json.dumps(match, ensure_ascii=False) + "\n")
                method_counts[match["method"]] = method_counts.get(match["method"], 0) + 1

    print(f"Records xử lý: {len(canonical)}")
    print("Số cặp (job, skill) theo phương pháp:", method_counts)
    print(f"job_skills -> {OUTPUT_PATH}")
    return str(OUTPUT_PATH)


if __name__ == "__main__":
    run()
