from src.process.extract_skills import (
    common_tokens,
    extract_from_source_field,
    extract_from_text,
)
from src.process.skill_dictionary import SkillDictionary


def _sample_dict() -> SkillDictionary:
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    skill_dict.add("C++", "hard", ["c++"])
    skill_dict.add("C", "hard", ["c"])
    skill_dict.add("Làm việc nhóm", "soft", ["làm việc nhóm"])
    skill_dict.add("AutoCAD", "hard", ["autocad"])
    return skill_dict


def test_extract_from_source_field_uses_given_skills_directly():
    rec = {"extra": {"skills_given": ["python", "unknown-skill"]}}
    matches = extract_from_source_field(rec, _sample_dict())
    assert len(matches) == 1
    assert matches[0]["canonical_name"] == "Python"
    assert matches[0]["method"] == "source_provided"


def test_exact_match_distinguishes_c_from_cpp():
    rec = {"title": "Lập trình C/C++", "requirements_raw": None, "description": None}
    matches = extract_from_text(rec, _sample_dict(), single_word_aliases=[])
    names = {m["canonical_name"] for m in matches}
    assert names == {"C", "C++"}


def test_exact_match_multiword_alias():
    rec = {
        "title": "Nhân viên",
        "requirements_raw": "Có khả năng làm việc nhóm hiệu quả",
        "description": None,
    }
    matches = extract_from_text(rec, _sample_dict(), single_word_aliases=[])
    assert any(m["canonical_name"] == "Làm việc nhóm" and m["skill_type"] == "soft" for m in matches)


def test_fuzzy_match_catches_typo_with_context():
    rec = {"title": "Kỹ sư", "requirements_raw": "Thành thạo autocard, excel", "description": None}
    matches = extract_from_text(rec, _sample_dict(), single_word_aliases=["autocad"])
    fuzzy = [m for m in matches if m["method"] == "fuzzy_match"]
    assert fuzzy and fuzzy[0]["canonical_name"] == "AutoCAD"
    assert "autocard" in fuzzy[0]["evidence"]


def test_no_skills_returns_empty_list():
    rec = {"title": "Nhân viên bảo vệ", "requirements_raw": "Sức khỏe tốt", "description": None}
    assert extract_from_text(rec, _sample_dict(), single_word_aliases=[]) == []


def test_common_tokens_flags_words_that_appear_in_too_many_records():
    records = [{"description": "testing pipeline"} for _ in range(50)]
    records.append({"description": "posgresql tuning"})
    common = common_tokens(records)
    assert "testing" in common
    assert "posgresql" not in common


def test_fuzzy_skips_common_words_so_testing_does_not_become_testng():
    """Hai từ chỉ cách nhau một phép xoá và vượt ngưỡng Levenshtein; chặn theo tần
    suất tài liệu mới tách được lỗi gõ thật khỏi từ thông dụng."""
    skills = SkillDictionary()
    skills.add("TestNG", "hard", ["testng"])
    rec = {"description": "Unit and integration testing APIs"}

    without_gate = extract_from_text(rec, skills, single_word_aliases=["testng"])
    assert [m["skill_id"] for m in without_gate] == ["testng"]

    with_gate = extract_from_text(
        rec, skills, single_word_aliases=["testng"], common=frozenset({"testing"})
    )
    assert with_gate == []


def test_fuzzy_still_catches_a_rare_typo():
    skills = SkillDictionary()
    skills.add("PostgreSql", "hard", ["postgresql"])
    rec = {"description": "Experience with posgresql required"}
    matches = extract_from_text(
        rec, skills, single_word_aliases=["postgresql"], common=frozenset({"experience"})
    )
    assert [m["skill_id"] for m in matches] == ["postgresql"]
