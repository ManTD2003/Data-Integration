from src.warehouse.build_warehouse import (
    _guess_city,
    _months_experience,
    _parse_salary,
    _role_family,
    build_dim_skill,
)


def test_parse_salary_splits_vieclam24h_range():
    rec = {"source": "vieclam24h", "salary_raw": "15000000-20000000"}
    assert _parse_salary(rec) == (15000000.0, 20000000.0)


def test_parse_salary_handles_partial_range():
    rec = {"source": "vieclam24h", "salary_raw": "None-20000000"}
    assert _parse_salary(rec) == (None, 20000000.0)


def test_parse_salary_uses_single_value_for_data_jobs():
    rec = {"source": "data_jobs", "salary_raw": "95000"}
    assert _parse_salary(rec) == (95000.0, 95000.0)


def test_parse_salary_missing_returns_none():
    assert _parse_salary({"source": "itviec", "salary_raw": None}) == (None, None)


def test_guess_city_takes_last_comma_segment():
    assert _guess_city("Thành phố Thủ Đức, Hồ Chí Minh") == "Hồ Chí Minh"
    assert _guess_city(None) is None


def test_months_experience_parses_itviec_level():
    assert _months_experience("37 months") == 37
    assert _months_experience(None) is None
    assert _months_experience("senior") is None


def test_role_family_uses_source_specific_field():
    assert _role_family({"source": "data_jobs", "extra": {"job_title_short": "Data Engineer"}}) == "Data Engineer"
    assert _role_family({"source": "vieclam24h", "extra": {"query": "marketing"}}) == "marketing"
    assert _role_family({"source": "itviec", "extra": {}}) is None


def test_build_dim_skill_fills_category_from_parent():
    skills = [
        {"skill_id": "cat", "canonical_name": "Ngôn ngữ lập trình", "skill_type": "hard", "parent_skill_id": None},
        {"skill_id": "py", "canonical_name": "Python", "skill_type": "hard", "parent_skill_id": "cat"},
    ]
    df = build_dim_skill(skills)
    row = df[df["skill_id"] == "py"].iloc[0]
    assert row["category"] == "Ngôn ngữ lập trình"
