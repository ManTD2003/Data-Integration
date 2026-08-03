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


def test_merge_keeps_parent_of_absorbed_cluster():
    skill_dict = SkillDictionary()
    category_id = skill_dict.add("Phát triển Backend", "hard", ["phát triển backend"])
    skill_dict.add("node", "hard", ["node"])
    skill_dict.add("NodeJS", "hard", ["nodejs"])
    skill_dict.lookup("nodejs")["parent_skill_id"] = category_id

    merged, _, old_to_new = resolve(_dict_to_skills(skill_dict))

    node_id = old_to_new[skill_dict.lookup("node")["skill_id"]]
    assert merged.skills[node_id]["parent_skill_id"] == old_to_new[category_id]


def test_parent_pointing_at_absorbed_skill_is_remapped():
    skill_dict = SkillDictionary()
    kept = skill_dict.add("Power BI", "hard", ["power bi"])
    absorbed = skill_dict.add("PowerBI", "hard", ["powerbi"])
    skill_dict.add("DAX", "hard", ["dax"])
    skill_dict.lookup("dax")["parent_skill_id"] = absorbed

    merged, _, old_to_new = resolve(_dict_to_skills(skill_dict))

    dax_parent = merged.skills[old_to_new[skill_dict.lookup("dax")["skill_id"]]]["parent_skill_id"]
    assert dax_parent in merged.skills
    assert dax_parent == old_to_new[kept] == old_to_new[absorbed]


def test_skill_is_never_its_own_parent_after_merge():
    skill_dict = SkillDictionary()
    parent = skill_dict.add("react", "hard", ["react"])
    skill_dict.add("ReactJS", "hard", ["reactjs"])
    skill_dict.lookup("reactjs")["parent_skill_id"] = parent

    merged, _, _ = resolve(_dict_to_skills(skill_dict))

    assert all(e["parent_skill_id"] != e["skill_id"] for e in merged.skills.values())


def test_unrelated_skills_stay_separate():
    skill_dict = SkillDictionary()
    skill_dict.add("SQL", "hard", ["sql"])
    skill_dict.add("MySQL", "hard", ["mysql"])
    skill_dict.add("Java", "hard", ["java"])
    skill_dict.add("JavaScript", "hard", ["javascript"])

    merged, log, _ = resolve(_dict_to_skills(skill_dict))
    assert len(merged.skills) == 4
    assert log == []
