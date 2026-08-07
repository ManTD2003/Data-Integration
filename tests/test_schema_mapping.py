from src.integration.schema_mapping import (
    _first_place,
    _skill_list,
    map_data_jobs,
    map_itviec,
    map_vieclam24h,
)


def test_first_place_parses_json_string():
    raw = '[{"province_id":120,"address":"874 Bui Huu Nghia","lat":10.9}]'
    place = _first_place(raw)
    assert (place["address"], place["province_id"]) == ("874 Bui Huu Nghia", 120)


def test_first_place_handles_empty():
    assert _first_place(None) == {}
    assert _first_place("[]") == {}


def test_skill_list_parses_repr():
    assert _skill_list("['python', 'sql']") == ["python", "sql"]
    assert _skill_list(None) == []


def test_map_vieclam24h_core_fields():
    raw = {
        "id": 123,
        "title": "Lap trinh vien Python",
        "employer_info": {"name": "Cong ty ABC"},
        "places": '[{"address":"Ha Noi"}]',
        "salary_min": 15000000,
        "salary_max": 20000000,
        "level_requirement": 5,
        "other_requirement": "<ul><li>Thanh thao Python</li></ul>",
        "created_at": 1784515379,
    }
    rec = map_vieclam24h(raw)
    assert rec.source == "vieclam24h"
    assert rec.source_id == "123"
    assert rec.company == "Cong ty ABC"
    assert rec.location == "Ha Noi"
    assert rec.salary_raw == "15000000-20000000"
    assert "Python" in rec.requirements_raw


def test_map_vieclam24h_carries_province_code_for_location_normalisation():
    raw = {
        "id": 1,
        "title": "Ky su",
        "places": '[{"province_id":122,"address":"617A Au Co"}]',
        "contact_address": "617A Au Co Phuong Tan Phu, Quan Tan Phu",
    }
    rec = map_vieclam24h(raw)
    assert rec.extra["province_id"] == 122
    assert rec.extra["contact_address"] == "617A Au Co Phuong Tan Phu, Quan Tan Phu"


def test_map_data_jobs_uses_skill_list():
    raw = {
        "_row_id": 7,
        "job_title": "Data Analyst",
        "company_name": "HPE",
        "job_location": "Mexico",
        "job_skills": "['python', 'sql', 'power bi']",
        "job_posted_date": "2023-01-14 13:18:07",
    }
    rec = map_data_jobs(raw)
    assert rec.source_id == "7"
    assert rec.requirements_raw == "python, sql, power bi"
    assert rec.extra["skills_given"] == ["python", "sql", "power bi"]
    assert str(rec.posted_date) == "2023-01-14"


def test_map_itviec_core_fields():
    raw = {
        "job_key": "abc-123",
        "slug": "data-engineer-lg",
        "title": "Data Engineer",
        "company": "LG CNS",
        "location": "Thu Duc, Ho Chi Minh",
        "skills": ["AWS"],
        "skills_ld": ["AWS", "Python", "SQL"],
        "requirements": "3 years python experience",
        "date_posted": "2026-07-16",
        "valid_through": "2026-08-20",
        "employment_type": "FULL_TIME",
        "months_experience": 37,
        "url": "https://itviec.com/it-jobs/data-engineer-lg",
    }
    rec = map_itviec(raw)
    assert rec.source_id == "abc-123"
    assert rec.company == "LG CNS"
    assert rec.requirements_raw == "3 years python experience"
    assert rec.extra["skills_given"] == ["AWS", "Python", "SQL"]
    assert str(rec.posted_date) == "2026-07-16"
    assert rec.job_type == "FULL_TIME"
    assert rec.level == "37 months"
    assert rec.extra["valid_through"] == "2026-08-20"
