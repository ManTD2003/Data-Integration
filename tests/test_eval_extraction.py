from src.eval.extraction import evaluate
from src.process.skill_dictionary import SkillDictionary


def _dictionary() -> SkillDictionary:
    skill_dict = SkillDictionary()
    skill_dict.add("Python", "hard", ["python"])
    skill_dict.add("Docker", "hard", ["docker"])
    skill_dict.add("Java", "hard", ["java"])
    return skill_dict


def test_evaluate_compares_text_matches_against_source_labels():
    skill_dict = _dictionary()
    records = [
        {
            "source": "itviec",
            "title": "Backend Developer",
            "requirements_raw": "Thành thạo Python, biết Docker là lợi thế",
            "description": None,
            "extra": {"skills_given": ["Python", "Docker"]},
        }
    ]

    result = evaluate(records, skill_dict, ["python", "docker"])

    assert result["n_records"] == 1
    assert result["overall"]["recall"] == 1.0
    assert result["overall"]["precision"] == 1.0


def test_missed_skill_lowers_recall():
    skill_dict = _dictionary()
    records = [
        {
            "source": "itviec",
            "title": "Backend Developer",
            "requirements_raw": "Thành thạo Python",
            "description": None,
            "extra": {"skills_given": ["Python", "Java"]},
        }
    ]

    result = evaluate(records, skill_dict, ["python", "docker"])
    assert result["overall"]["recall"] == 0.5
    assert result["overall"]["fn"] == 1


def test_data_jobs_is_measured_on_title_only():
    """requirements_raw của data_jobs chính là danh sách nhãn, dùng nó sẽ tự cho điểm."""
    skill_dict = _dictionary()
    records = [
        {
            "source": "data_jobs",
            "title": "Data Engineer",
            "requirements_raw": "python, docker",
            "description": None,
            "extra": {"skills_given": ["Python", "Docker"]},
        }
    ]

    result = evaluate(records, skill_dict, ["python", "docker"])
    assert result["overall"]["tp"] == 0
    assert result["overall"]["fn"] == 2


def test_records_without_labels_are_skipped():
    skill_dict = _dictionary()
    records = [
        {"source": "vieclam24h", "title": "Lập trình Python", "extra": {}},
        {"source": "itviec", "title": "Dev", "extra": {"skills_given": []}},
    ]
    assert evaluate(records, skill_dict, ["python"])["n_records"] == 0
