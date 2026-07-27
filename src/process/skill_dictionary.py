"""Từ điển kỹ năng mầm: nền cho gazetteer/fuzzy matching ở extract_skills.py.

Nguồn: (1) khai thác skills_given có sẵn từ itviec/data_jobs (mỏ dữ liệu miễn phí,
đã được nguồn tự gắn nhãn); (2) bổ sung tay cho các ngành ngoài IT (vieclam24h đa
ngành: kế toán, marketing, xây dựng, bán hàng...) và kỹ năng mềm chung, vì hai
nguồn IT không phủ được nhóm này.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from src.common.paths import STAGING

DICTIONARY_PATH = STAGING / "skill_dictionary.json"

# Kỹ năng mined từ skills_given thường là công cụ/công nghệ cụ thể (hard). Vài mục
# mang tính quản lý/con người thì cần gắn lại thành soft.
SOFT_OVERRIDES = {
    "leadership",
    "team management",
    "stakeholder management",
    "communication",
    "japanese it communication",
}

# (canonical_name, skill_type, [alias,...]) — alias dùng để đối sánh, không phân
# biệt hoa/thường và dấu.
SUPPLEMENT: list[tuple[str, str, list[str]]] = [
    ("Giao tiếp", "soft", ["giao tiếp", "kỹ năng giao tiếp", "communication skill"]),
    ("Làm việc nhóm", "soft", ["làm việc nhóm", "team work", "teamwork"]),
    ("Quản lý thời gian", "soft", ["quản lý thời gian", "time management"]),
    ("Giải quyết vấn đề", "soft", ["giải quyết vấn đề", "problem solving"]),
    ("Tư duy phản biện", "soft", ["tư duy phản biện", "critical thinking"]),
    ("Chịu áp lực công việc", "soft", ["chịu áp lực", "chịu được áp lực cao", "work under pressure"]),
    ("Đàm phán", "soft", ["đàm phán", "negotiation"]),
    ("Thuyết trình", "soft", ["thuyết trình", "presentation skill"]),
    ("Chăm chỉ", "soft", ["chăm chỉ", "chịu khó", "siêng năng"]),
    ("Trung thực", "soft", ["trung thực", "honest"]),
    ("Cẩn thận, tỉ mỉ", "soft", ["cẩn thận", "tỉ mỉ"]),
    ("Chủ động trong công việc", "soft", ["chủ động", "proactive"]),
    ("Tinh thần trách nhiệm", "soft", ["tinh thần trách nhiệm", "trách nhiệm trong công việc"]),
    ("Kỹ năng quản lý", "soft", ["kỹ năng quản lý", "quản lý nhân sự"]),
    ("Bán hàng", "hard", ["bán hàng", "kỹ năng bán hàng", "sales skill", "kinh doanh"]),
    ("Chăm sóc khách hàng", "hard", ["chăm sóc khách hàng", "customer service", "cskh"]),
    ("Telesale", "hard", ["telesale", "tư vấn qua điện thoại"]),
    ("Tuyển dụng", "hard", ["tuyển dụng", "recruitment"]),
    ("Tính lương, C&B", "hard", ["c&b", "tính lương", "compensation and benefits"]),
    ("Kế toán thuế", "hard", ["kế toán thuế", "kê khai thuế", "tax accounting"]),
    ("Kế toán công nợ", "hard", ["kế toán công nợ", "kế toán thanh toán"]),
    ("Phần mềm kế toán MISA", "hard", ["misa", "phần mềm kế toán misa"]),
    ("Tin học văn phòng", "hard", ["tin học văn phòng", "microsoft office", "ms office"]),
    ("Word", "hard", ["word", "microsoft word"]),
    ("Photoshop", "hard", ["photoshop"]),
    ("Adobe Illustrator", "hard", ["illustrator", "adobe illustrator"]),
    ("Adobe Premiere", "hard", ["premiere", "adobe premiere"]),
    ("CorelDRAW", "hard", ["corel", "coreldraw"]),
    ("AutoCAD", "hard", ["autocad"]),
    ("SEO", "hard", ["seo"]),
    ("Content Marketing", "hard", ["content marketing", "viết content"]),
    ("Digital Marketing", "hard", ["digital marketing"]),
    ("Social Media Marketing", "hard", ["social media", "mạng xã hội", "mxh"]),
    ("Quảng cáo Facebook", "hard", ["facebook ads", "quảng cáo facebook"]),
    ("Quảng cáo Google", "hard", ["google ads", "quảng cáo google"]),
    ("Quản lý dự án", "hard", ["quản lý dự án", "project management"]),
    ("Giám sát công trình", "hard", ["giám sát công trình", "giám sát thi công"]),
    ("Dự toán xây dựng", "hard", ["dự toán xây dựng", "bóc tách khối lượng"]),
    ("Đọc bản vẽ kỹ thuật", "hard", ["đọc bản vẽ", "bản vẽ kỹ thuật"]),
    ("Tiếng Anh", "hard", ["tiếng anh", "english"]),
    ("Tiếng Trung", "hard", ["tiếng trung", "chinese"]),
    ("Tiếng Nhật", "hard", ["tiếng nhật", "japanese"]),
    ("Tiếng Hàn", "hard", ["tiếng hàn", "korean"]),
]


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().strip()
    return re.sub(r"\s+", " ", text)


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "skill"


def _pick_display_form(variants: Counter) -> str:
    """Ưu tiên biến thể có chữ hoa (tên riêng/viết tắt chuẩn ngành) làm tên hiển thị."""
    proper_cased = {v: c for v, c in variants.items() if any(ch.isupper() for ch in v)}
    pool = proper_cased or variants
    return max(pool.items(), key=lambda kv: kv[1])[0]


class SkillDictionary:
    def __init__(self) -> None:
        self.skills: dict[str, dict] = {}
        self.alias_index: dict[str, str] = {}

    def _new_skill(self, skill_id: str, canonical_name: str, skill_type: str) -> None:
        self.skills[skill_id] = {
            "skill_id": skill_id,
            "canonical_name": canonical_name,
            "skill_type": skill_type,
            "aliases": [],
        }

    def add(self, canonical_name: str, skill_type: str, aliases: list[str]) -> str:
        all_aliases = {_fold(canonical_name), *[_fold(a) for a in aliases]}
        existing_id = next((self.alias_index[a] for a in all_aliases if a in self.alias_index), None)

        if existing_id is None:
            skill_id = _slugify(canonical_name)
            suffix = 2
            while skill_id in self.skills:
                skill_id = f"{_slugify(canonical_name)}-{suffix}"
                suffix += 1
            self._new_skill(skill_id, canonical_name, skill_type)
            existing_id = skill_id

        entry = self.skills[existing_id]
        for alias in all_aliases:
            self.alias_index[alias] = existing_id
            if alias not in entry["aliases"]:
                entry["aliases"].append(alias)
        return existing_id

    def lookup(self, alias: str) -> dict | None:
        skill_id = self.alias_index.get(_fold(alias))
        return self.skills.get(skill_id) if skill_id else None

    def to_json(self) -> list[dict]:
        return list(self.skills.values())


def _mine_from_records(records: list[dict]) -> Counter:
    """Đếm tần suất từng biến thể chữ trong skills_given (itviec + data_jobs)."""
    variants: Counter = Counter()
    for rec in records:
        for raw_skill in rec.get("extra", {}).get("skills_given") or []:
            name = raw_skill.strip()
            if name:
                variants[name] += 1
    return variants


def build_dictionary(records: list[dict]) -> SkillDictionary:
    mined = _mine_from_records(records)
    grouped: dict[str, Counter] = {}
    for name, count in mined.items():
        grouped.setdefault(_fold(name), Counter())[name] += count

    skill_dict = SkillDictionary()
    for folded, variants in grouped.items():
        skill_type = "soft" if folded in SOFT_OVERRIDES else "hard"
        display_name = _pick_display_form(variants)
        skill_dict.add(display_name, skill_type, list(variants))

    for canonical_name, skill_type, aliases in SUPPLEMENT:
        skill_dict.add(canonical_name, skill_type, aliases)

    return skill_dict


def load_or_build(records: list[dict], force_rebuild: bool = False) -> SkillDictionary:
    if not force_rebuild and DICTIONARY_PATH.exists():
        skill_dict = SkillDictionary()
        for entry in json.loads(DICTIONARY_PATH.read_text(encoding="utf-8")):
            skill_dict.skills[entry["skill_id"]] = entry
            for alias in entry["aliases"]:
                skill_dict.alias_index[alias] = entry["skill_id"]
        return skill_dict

    skill_dict = build_dictionary(records)
    DICTIONARY_PATH.write_text(
        json.dumps(skill_dict.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return skill_dict


def run() -> str:
    records_path = STAGING / "records_deduped.jsonl"
    records = [json.loads(line) for line in open(records_path, encoding="utf-8")]
    skill_dict = load_or_build(records, force_rebuild=True)

    hard = sum(1 for s in skill_dict.skills.values() if s["skill_type"] == "hard")
    soft = sum(1 for s in skill_dict.skills.values() if s["skill_type"] == "soft")
    print(f"Skills: {len(skill_dict.skills)} (hard={hard}, soft={soft}) | aliases: {len(skill_dict.alias_index)}")
    print(f"Từ điển -> {DICTIONARY_PATH}")
    return str(DICTIONARY_PATH)


if __name__ == "__main__":
    run()
