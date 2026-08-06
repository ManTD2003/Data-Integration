"""Entity resolution cho biến thể kỹ năng: gộp các skill_id lẽ ra là cùng một kỹ
năng nhưng bị tách vì cách viết khác nhau (react/ReactJS/react.js, mongo/MongoDB...).

Đã thử TF-IDF ký tự n-gram (cosine similarity) trước khi chọn cách này, nhưng
không tìm được ngưỡng an toàn: react/reactjs đạt 0.73 trong khi sql/mysql đã 0.55
và "excel"/"excel vba" đạt 0.64 — quá gần nhau để chọn một ngưỡng chung mà không
gộp nhầm các cặp khác nghĩa (kiểu java/javascript). Nên dùng luật tách hậu tố
".../js" (bắt các biến thể framework JS) cộng danh sách gộp thủ công đã soát qua
toàn bộ từ điển cho các viết tắt bất quy tắc (mongo, golang, pentest...).
"""

from __future__ import annotations

import json
import re

from src.common.paths import STAGING
from src.process.skill_dictionary import DICTIONARY_PATH, SkillDictionary, _fold

JOB_SKILLS_PATH = STAGING / "job_skills.jsonl"
MERGE_LOG_PATH = STAGING / "skill_merge_log.json"

CURATED_MERGES = [
    ("mongo", "mongodb"),
    ("go", "golang"),
    ("aurora", "amazon aurora"),
    ("power bi", "powerbi"),
    ("pentest", "penetration testing"),
    ("rpa", "robotic process automation (rpa)"),
    ("photoshop", "adobe photoshop"),
    ("c", "c language"),
]


MIN_JS_CORE_LEN = 3

# Cặp tên gần nhau nhưng khác nghĩa; chặn tường minh để một luật chuẩn hoá thêm vào
# sau này không âm thầm gộp chúng.
PROTECTED_PAIRS = {
    frozenset({"java", "javascript"}),
    frozenset({"sql", "mysql"}),
    frozenset({"c", "c++"}),
    frozenset({"c", "c#"}),
    frozenset({"react", "react native"}),
}


def _strip_js_suffix(folded: str) -> str:
    # Chỉ bỏ dấu phân cách (khoảng trắng/dấu chấm/gạch), KHÔNG bỏ +/# — nếu không
    # C, C++, C# đều rơi về cùng một khoá "c" (lỗi đã gặp khi thử phiên bản đầu).
    core = re.sub(r"[\s\-_.]", "", folded)
    if core.endswith("js") and len(core) - 2 >= MIN_JS_CORE_LEN:
        return core[:-2]
    return core


def _protected(a: dict, b: dict) -> bool:
    pair = frozenset({_fold(a["canonical_name"]), _fold(b["canonical_name"])})
    return pair in PROTECTED_PAIRS


def _cluster(skills: list[dict]) -> dict[str, str]:
    parent = {s["skill_id"]: s["skill_id"] for s in skills}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    by_id = {s["skill_id"]: s for s in skills}
    by_alias: dict[str, str] = {}
    by_suffix_key: dict[tuple[str, str], list[str]] = {}
    for s in skills:
        for alias in s["aliases"]:
            by_alias[alias] = s["skill_id"]
        key = (_strip_js_suffix(_fold(s["canonical_name"])), s["skill_type"])
        by_suffix_key.setdefault(key, []).append(s["skill_id"])

    for ids in by_suffix_key.values():
        for other in ids[1:]:
            if _protected(by_id[ids[0]], by_id[other]):
                continue
            union(ids[0], other)

    for alias_a, alias_b in CURATED_MERGES:
        id_a, id_b = by_alias.get(alias_a), by_alias.get(alias_b)
        if id_a and id_b and not _protected(by_id[id_a], by_id[id_b]):
            union(id_a, id_b)

    return {sid: find(sid) for sid in parent}


def _remap_job_skills(old_to_new: dict[str, str], skill_dict: SkillDictionary) -> None:
    if not JOB_SKILLS_PATH.exists():
        return

    best: dict[tuple[str, str], dict] = {}
    method_rank = {"source_provided": 0, "exact_match": 1, "fuzzy_match": 2}
    with open(JOB_SKILLS_PATH, encoding="utf-8") as f:
        for line in f:
            match = json.loads(line)
            new_id = old_to_new.get(match["skill_id"], match["skill_id"])
            skill = skill_dict.skills[new_id]
            match["skill_id"] = new_id
            match["canonical_name"] = skill["canonical_name"]
            match["skill_type"] = skill["skill_type"]

            key = (match["record_id"], new_id)
            current = best.get(key)
            if current is None or method_rank[match["method"]] < method_rank[current["method"]]:
                best[key] = match

    with open(JOB_SKILLS_PATH, "w", encoding="utf-8") as f:
        for match in best.values():
            f.write(json.dumps(match, ensure_ascii=False) + "\n")


def resolve(skills: list[dict]) -> tuple[SkillDictionary, list[dict], dict[str, str]]:
    skill_by_id = {s["skill_id"]: s for s in skills}
    remap = _cluster(skills)

    groups: dict[str, list[dict]] = {}
    for old_id, rep_id in remap.items():
        groups.setdefault(rep_id, []).append(skill_by_id[old_id])

    merged_dict = SkillDictionary()
    log: list[dict] = []
    old_to_new: dict[str, str] = {}
    for members in groups.values():
        members.sort(key=lambda s: len(s["aliases"]), reverse=True)
        head = members[0]
        all_aliases = sorted({a for m in members for a in m["aliases"]})
        new_id = merged_dict.add(head["canonical_name"], head["skill_type"], all_aliases)
        # SkillDictionary.add() luôn khởi tạo parent rỗng, nên phải mang lại quan hệ
        # cha-con của cụm; nếu không, chạy lại bước này sau build_hierarchy sẽ xoá
        # sạch phân cấp mà kho vẫn nạp bình thường.
        parent_id = next((m["parent_skill_id"] for m in members if m.get("parent_skill_id")), None)
        merged_dict.skills[new_id]["parent_skill_id"] = parent_id
        merged_dict.skills[new_id]["is_category"] = any(m.get("is_category") for m in members)
        for m in members:
            old_to_new[m["skill_id"]] = new_id
        if len(members) > 1:
            log.append(
                {
                    "kept": head["canonical_name"],
                    "absorbed": [m["canonical_name"] for m in members[1:]],
                }
            )

    for entry in merged_dict.skills.values():
        parent_id = entry["parent_skill_id"]
        if not parent_id:
            continue
        new_parent = old_to_new.get(parent_id, parent_id)
        entry["parent_skill_id"] = None if new_parent == entry["skill_id"] else new_parent

    return merged_dict, log, old_to_new


def run() -> str:
    skills = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    merged_dict, log, old_to_new = resolve(skills)

    DICTIONARY_PATH.write_text(
        json.dumps(merged_dict.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    MERGE_LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    _remap_job_skills(old_to_new, merged_dict)

    print(f"Skills: {len(skills)} -> {len(merged_dict.skills)} (gộp {len(log)} cụm)")
    print(f"Log gộp -> {MERGE_LOG_PATH}")
    return str(DICTIONARY_PATH)


if __name__ == "__main__":
    run()
