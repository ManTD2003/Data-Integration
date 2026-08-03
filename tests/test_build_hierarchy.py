from src.process.build_hierarchy import assign_parents, build_closure
from src.process.skill_dictionary import SkillDictionary


def test_assign_parents_links_known_skill_to_category():
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    skill_dict.add("Java", "hard", ["java"])

    missing = assign_parents(skill_dict)

    python_parent = skill_dict.lookup("python")["parent_skill_id"]
    java_parent = skill_dict.lookup("java")["parent_skill_id"]
    assert python_parent == java_parent
    assert skill_dict.skills[python_parent]["canonical_name"] == "Ngôn ngữ lập trình"
    assert "Python" not in missing


def test_assign_parents_reports_names_not_in_dictionary():
    skill_dict = SkillDictionary()
    missing = assign_parents(skill_dict)
    assert "Python" in missing
    assert "Java" in missing


def test_soft_skills_roll_up_to_soft_root():
    skill_dict = SkillDictionary()
    skill_dict.add("Giao tiếp", "soft", ["giao tiếp"])
    assign_parents(skill_dict)

    entry = skill_dict.lookup("giao tiếp")
    root = skill_dict.skills[entry["parent_skill_id"]]
    assert root["canonical_name"] == "Kỹ năng mềm"
    assert root["skill_type"] == "soft"


def test_closure_table_has_self_and_parent_rows():
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    assign_parents(skill_dict)

    closure = build_closure(skill_dict)
    python_id = skill_dict.lookup("python")["skill_id"]
    parent_id = skill_dict.lookup("python")["parent_skill_id"]

    assert {"ancestor_id": python_id, "descendant_id": python_id, "depth": 0} in closure
    assert {"ancestor_id": parent_id, "descendant_id": python_id, "depth": 1} in closure


def test_category_rolls_up_to_root_group():
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    assign_parents(skill_dict)

    category = skill_dict.skills[skill_dict.lookup("python")["parent_skill_id"]]
    root = skill_dict.skills[category["parent_skill_id"]]
    assert root["canonical_name"] == "Kỹ năng công nghệ thông tin"
    assert root["parent_skill_id"] is None


def test_closure_reaches_leaf_from_root():
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    assign_parents(skill_dict)

    closure = build_closure(skill_dict)
    python_id = skill_dict.lookup("python")["skill_id"]
    root_id = skill_dict.lookup("kỹ năng công nghệ thông tin")["skill_id"]

    assert {"ancestor_id": root_id, "descendant_id": python_id, "depth": 2} in closure


def test_closure_stops_on_cyclic_parent():
    skill_dict = SkillDictionary()
    first = skill_dict.add("A", "hard", ["a"])
    second = skill_dict.add("B", "hard", ["b"])
    skill_dict.skills[first]["parent_skill_id"] = second
    skill_dict.skills[second]["parent_skill_id"] = first

    closure = build_closure(skill_dict)

    assert len(closure) == 4
    assert max(row["depth"] for row in closure) == 1
