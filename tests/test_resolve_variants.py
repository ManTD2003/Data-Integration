from src.process.resolve_variants import resolve
from src.process.skill_dictionary import SkillDictionary


def _dict_to_skills(skill_dict: SkillDictionary) -> list[dict]:
    return skill_dict.to_json()


def test_js_suffix_rule_merges_framework_variants():
    skill_dict = SkillDictionary()
    skill_dict.add("react", "hard", ["react"])
    skill_dict.add("ReactJS", "hard", ["reactjs"])
    skill_dict.add("node", "hard", ["node"])
    skill_dict.add("node.js", "hard", ["node.js"])
    skill_dict.add("NodeJS", "hard", ["nodejs"])

    merged, log, _ = resolve(_dict_to_skills(skill_dict))
    assert len(merged.skills) == 2
    assert {e["absorbed"][0] for e in log if e["kept"] == "react"} == {"ReactJS"}


def test_symbol_suffix_does_not_collapse_c_variants():
    skill_dict = SkillDictionary()
    skill_dict.add("c", "hard", ["c"])
    skill_dict.add("C++", "hard", ["c++"])
    skill_dict.add("C#", "hard", ["c#"])

    merged, log, _ = resolve(_dict_to_skills(skill_dict))
    assert len(merged.skills) == 3
    assert log == []


def test_curated_merge_applies_known_abbreviation():
    skill_dict = SkillDictionary()
    skill_dict.add("mongo", "hard", ["mongo"])
    skill_dict.add("MongoDB", "hard", ["mongodb"])

    merged, log, old_to_new = resolve(_dict_to_skills(skill_dict))
    assert len(merged.skills) == 1
    assert len(set(old_to_new.values())) == 1


def test_unrelated_skills_stay_separate():
    skill_dict = SkillDictionary()
    skill_dict.add("SQL", "hard", ["sql"])
    skill_dict.add("MySQL", "hard", ["mysql"])
    skill_dict.add("Java", "hard", ["java"])
    skill_dict.add("JavaScript", "hard", ["javascript"])

    merged, log, _ = resolve(_dict_to_skills(skill_dict))
    assert len(merged.skills) == 4
    assert log == []
