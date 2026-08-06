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
from src.common.schema import strip_accents

DICTIONARY_PATH = STAGING / "skill_dictionary.json"

# Tag của nguồn trộn lẫn kỹ năng với tên vị trí tuyển dụng. Giữ lại tên vị trí thì
# gazetteer khớp "Senior Data Engineer" thành kỹ năng "Data Engineer" — sai loại
# thực thể, và làm bẩn cả bảng xếp hạng nhu cầu kỹ năng.
ROLE_TERMS = {
    "data engineer",
    "data scientist",
    "data analyst",
    "software engineer",
    "bridge engineer",
    "product owner",
    "tester",
    "qa qc",
    "system admin",
    "presale",
}

# Viết tắt thông dụng không xuất hiện trong tag của nguồn nên không mine được.
# Chỉ nhận các viết tắt không nhập nhằng: "js"/"ts"/"ml" bị loại vì chúng cũng là
# token thường gặp trong văn bản tiếng Việt, thêm vào sẽ sinh dương tính giả.
EXTRA_ALIASES: dict[str, list[str]] = {
    "Kubernetes": ["k8s"],
    "PostgreSql": ["postgres"],
}

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


# NFKD không tách được "đ" và mọi ký hiệu đều bị bỏ, nên C#/C++/C cùng rơi về slug
# "c" rồi phải phân biệt bằng hậu tố số theo thứ tự chèn — nghĩa là cùng một skill_id
# có thể trỏ sang kỹ năng khác sau mỗi lần dựng lại từ điển. Phiên âm trước khi lọc.
SYMBOL_MAP = [
    ("c++", "c-plus-plus"),
    ("c#", "c-sharp"),
    ("f#", "f-sharp"),
    (".net", "-dotnet"),
    ("&", "-and-"),
    ("+", "-plus"),
    ("#", "-sharp"),
]


def _slugify(name: str) -> str:
    text = _fold(name)
    for symbol, replacement in SYMBOL_MAP:
        text = text.replace(symbol, replacement)
    slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(text)).strip("-")
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

    def _new_skill(self, skill_id: str, canonical_name: str, skill_type: str, is_category: bool) -> None:
        self.skills[skill_id] = {
            "skill_id": skill_id,
            "canonical_name": canonical_name,
            "skill_type": skill_type,
            "aliases": [],
            "parent_skill_id": None,
            "is_category": is_category,
        }

    def add(
        self, canonical_name: str, skill_type: str, aliases: list[str], is_category: bool = False
    ) -> str:
        all_aliases = {_fold(canonical_name), *[_fold(a) for a in aliases]}
        existing_id = next((self.alias_index[a] for a in all_aliases if a in self.alias_index), None)

        if existing_id is None:
            skill_id = _slugify(canonical_name)
            suffix = 2
            while skill_id in self.skills:
                skill_id = f"{_slugify(canonical_name)}-{suffix}"
                suffix += 1
            self._new_skill(skill_id, canonical_name, skill_type, is_category)
            existing_id = skill_id

        entry = self.skills[existing_id]
        for alias in all_aliases:
            self.alias_index[alias] = existing_id
            if alias not in entry["aliases"]:
                entry["aliases"].append(alias)
        return existing_id

    def for_extraction(self) -> SkillDictionary:
        """Bản từ điển bỏ các nút nhóm do bước phân cấp sinh ra.

        Nếu không lọc, chạy lại bước trích chọn sau bước phân cấp sẽ khớp thêm chính
        các nhãn nhóm ("ngôn ngữ lập trình", "cơ sở dữ liệu"...) mà bước trích chọn
        chạy trước đó không hề thấy — kết quả phụ thuộc thứ tự chạy.
        """
        view = SkillDictionary()
        for skill_id, entry in self.skills.items():
            if entry.get("is_category"):
                continue
            view.skills[skill_id] = entry
            for alias in entry["aliases"]:
                view.alias_index[alias] = skill_id
        return view

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
        folded = _fold(name)
        if folded in ROLE_TERMS:
            continue
        grouped.setdefault(folded, Counter())[name] += count

    skill_dict = SkillDictionary()
    for folded, variants in grouped.items():
        skill_type = "soft" if folded in SOFT_OVERRIDES else "hard"
        display_name = _pick_display_form(variants)
        skill_dict.add(display_name, skill_type, list(variants))

    for canonical_name, skill_type, aliases in SUPPLEMENT:
        skill_dict.add(canonical_name, skill_type, aliases)

    for canonical_name, aliases in EXTRA_ALIASES.items():
        entry = skill_dict.lookup(canonical_name)
        if entry is not None:
            skill_dict.add(entry["canonical_name"], entry["skill_type"], aliases)

    return skill_dict


def load_or_build(records: list[dict], force_rebuild: bool = False) -> SkillDictionary:
    if not force_rebuild and DICTIONARY_PATH.exists():
        skill_dict = SkillDictionary()
        for entry in json.loads(DICTIONARY_PATH.read_text(encoding="utf-8")):
            entry.setdefault("is_category", False)
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

    slugs = Counter(_slugify(s["canonical_name"]) for s in skill_dict.skills.values())
    collided = {slug: n for slug, n in slugs.items() if n > 1}
    if collided:
        print("Slug trùng, skill_id phải thêm hậu tố số:", collided)

    print(f"Từ điển -> {DICTIONARY_PATH}")
    return str(DICTIONARY_PATH)


if __name__ == "__main__":
    run()
