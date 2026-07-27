from src.process.skill_dictionary import SkillDictionary, build_dictionary


def test_merges_case_variants_into_one_skill():
    records = [
        {"extra": {"skills_given": ["python", "Python", "PYTHON"]}},
        {"extra": {"skills_given": ["sql"]}},
    ]
    skill_dict = build_dictionary(records)
    python_entry = skill_dict.lookup("python")
    assert python_entry is not None
    assert python_entry["canonical_name"] == "Python"
    assert python_entry["skill_type"] == "hard"


def test_soft_override_reclassifies_mined_skill():
    records = [{"extra": {"skills_given": ["Leadership", "leadership"]}}]
    skill_dict = build_dictionary(records)
    entry = skill_dict.lookup("leadership")
    assert entry["skill_type"] == "soft"


def test_supplement_covers_non_it_domains():
    skill_dict = build_dictionary([])
    assert skill_dict.lookup("kế toán công nợ") is not None
    assert skill_dict.lookup("kỹ năng giao tiếp")["skill_type"] == "soft"
    assert skill_dict.lookup("photoshop")["skill_type"] == "hard"


def test_lookup_is_accent_and_case_insensitive():
    skill_dict = SkillDictionary()
    skill_dict.add("Tiếng Anh", "hard", ["tiếng anh", "english"])
    assert skill_dict.lookup("Tiếng Anh")["skill_id"] == skill_dict.lookup("ENGLISH")["skill_id"]


def test_alias_shared_between_two_supplement_entries_does_not_merge_them():
    skill_dict = build_dictionary([])
    kt_thue = skill_dict.lookup("kế toán thuế")
    kt_no = skill_dict.lookup("kế toán công nợ")
    assert kt_thue["skill_id"] != kt_no["skill_id"]
