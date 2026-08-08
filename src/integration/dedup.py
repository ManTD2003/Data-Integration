from __future__ import annotations

import json
import re
from collections import defaultdict

from src.common.paths import STAGING
from src.common.schema import norm_text, strip_accents
from src.common.similarity import token_sort_levenshtein

TITLE_SIM = 87.5
COMPANY_SIM = 88
KEY_LEN = 12

# Tên doanh nghiệp Việt Nam gần như luôn mở đầu bằng loại hình pháp lý, nên 12 ký tự
# đầu của tên chưa cắt tiền tố chỉ là "cong ty tnhh"/"cong ty co p": hai khối đó nuốt
# gần hết bản ghi và blocking mất tác dụng.
LEGAL_TOKENS = {
    "cong", "ty", "cty", "tnhh", "co", "phan", "cp", "mtv", "mot", "thanh", "vien",
    "lien", "doanh", "tap", "doan", "thuong", "mai", "dich", "vu", "dau", "tu",
    "san", "xuat", "phat", "trien", "giai", "phap", "va", "and",
    "jsc", "joint", "stock", "company", "corporation", "corp", "inc", "ltd", "limited", "group",
}
NON_WORD = re.compile(r"[^a-z0-9 ]+")


def company_key(name: str | None) -> str:
    """Tên công ty đã bỏ dấu và cắt hết tiền tố loại hình doanh nghiệp.

    Cắt lặp chứ không cắt một lần: "Công ty TNHH MTV Thương mại XYZ" có bốn cụm loại
    hình nối nhau, bỏ sót cụm nào thì khoá vẫn rơi vào đúng chỗ nghẽn cũ.
    """
    tokens = " ".join(NON_WORD.sub(" ", strip_accents(name)).split()).split()
    trimmed = list(tokens)
    while trimmed and trimmed[0] in LEGAL_TOKENS:
        trimmed.pop(0)
    return " ".join(trimmed or tokens)


def blocking_key(rec: dict) -> str:
    company = company_key(rec.get("company"))
    if company:
        return company[:KEY_LEN]
    return strip_accents(rec.get("title"))[:KEY_LEN]


def is_duplicate(a: dict, b: dict) -> bool:
    """So khớp cả trong cùng nguồn lẫn giữa các nguồn.

    Cùng một vị trí đăng trên hai cổng là trường hợp trùng đáng phát hiện nhất, nên
    điều kiện không ràng buộc `source`; tên công ty được so sau khi đã bỏ dấu và cắt
    tiền tố loại hình để "Công ty TNHH ABC" và "ABC Co., Ltd" không bị coi là khác nhau.
    """
    title_sim = token_sort_levenshtein(norm_text(a["title"]), norm_text(b["title"]))
    if title_sim < TITLE_SIM:
        return False
    comp_sim = token_sort_levenshtein(company_key(a.get("company")), company_key(b.get("company")))
    return comp_sim >= COMPANY_SIM


def _richness(rec: dict) -> tuple[int, int]:
    """Bản ghi nào giữ lại làm đại diện: ưu tiên bản có nhãn kỹ năng sẵn, rồi tới bản
    có nhiều văn bản mô tả hơn — nếu không, gộp liên nguồn có thể vứt đúng bản ghi
    mang nhãn của nguồn."""
    extra = rec.get("extra") or {}
    labelled = 1 if extra.get("skills_given") else 0
    text = len(rec.get("requirements_raw") or "") + len(rec.get("description") or "")
    return labelled, text


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

    best: dict[int, int] = {}
    for i, rec in enumerate(records):
        gid = rec["dup_group_id"]
        if gid not in best or _richness(rec) > _richness(records[best[gid]]):
            best[gid] = i
    for i, rec in enumerate(records):
        rec["is_canonical"] = best[rec["dup_group_id"]] == i


def run() -> str:
    src = STAGING / "records.jsonl"
    records = [json.loads(line) for line in open(src, encoding="utf-8")]
    assign_groups(records)

    out = STAGING / "records_deduped.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    groups: dict[int, set[str]] = defaultdict(set)
    for rec in records:
        groups[rec["dup_group_id"]].add(rec["source"])
    canonical = sum(1 for r in records if r["is_canonical"])
    cross = sum(1 for sources in groups.values() if len(sources) > 1)
    print(
        f"Records: {len(records)} | groups: {len(groups)} | "
        f"duplicates removed: {len(records) - canonical} | nhóm liên nguồn: {cross}"
    )
    print(f"Deduped staging -> {out}")
    return str(out)


if __name__ == "__main__":
    run()
