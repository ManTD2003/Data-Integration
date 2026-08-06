from __future__ import annotations

import ast
import json
import sys
from datetime import date, datetime

from selectolax.parser import HTMLParser

from src.common.schema import JobRecord

# GAV: bảng ánh xạ trường-nguồn -> trường mediated, dùng cho báo cáo và name-based matcher.
FIELD_MAP = {
    "vieclam24h": {
        "id": "source_id",
        "title": "title",
        "employer_info.name": "company",
        "places[0].address": "location",
        "salary_min/salary_max": "salary_raw",
        "level_requirement": "level",
        "working_method": "job_type",
        "job_requirement": "description",
        "job_requirement+other_requirement": "requirements_raw",
        "created_at": "posted_date",
    },
    "data_jobs": {
        "_row_id": "source_id",
        "job_title": "title",
        "company_name": "company",
        "job_location": "location",
        "salary_year_avg": "salary_raw",
        "job_schedule_type": "job_type",
        "job_skills": "requirements_raw",
        "job_posted_date": "posted_date",
    },
    "itviec": {
        "job_key": "source_id",
        "title": "title",
        "company": "company",
        "location": "location",
        "salary_raw": "salary_raw",
        "employment_type": "job_type",
        "months_experience": "level",
        "requirements": "requirements_raw",
        "description": "description",
        "date_posted": "posted_date",
        "url": "url",
    },
}


def html_to_text(value: str | None) -> str | None:
    if not value:
        return None
    text = HTMLParser(value).text(separator=" ").strip()
    return " ".join(text.split()) or None


def _skill_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(x) for x in value]
    try:
        parsed = ast.literal_eval(value)
    except (ValueError, SyntaxError):
        # Nhãn kỹ năng hỏng nghĩa là mất toàn bộ kỹ năng của tin đó, phải nhìn thấy được.
        print(f"schema_mapping: không đọc được danh sách kỹ năng {value!r:.80}", file=sys.stderr)
        return []
    return [str(x) for x in parsed] if isinstance(parsed, list) else []


def _first_place(places) -> str | None:
    if not places:
        return None
    if isinstance(places, str):
        try:
            places = json.loads(places)
        except json.JSONDecodeError:
            return None
        if not places:
            return None
    first = places[0]
    if isinstance(first, dict):
        return first.get("address") or None
    return str(first) or None


def map_vieclam24h(raw: dict) -> JobRecord:
    employer = raw.get("employer_info") or {}
    location = _first_place(raw.get("places"))

    # Chỉ nối các giá trị thực có: "None-20000000" sẽ bị bước nạp kho đọc thành mức
    # lương tối thiểu 20 triệu.
    bounds = [str(v) for v in (raw.get("salary_min"), raw.get("salary_max")) if v]
    salary_raw = "-".join(bounds) or None

    req_parts = [
        html_to_text(raw.get("job_requirement")),
        html_to_text(raw.get("other_requirement")),
    ]
    requirements = " ".join(p for p in req_parts if p) or None

    posted = None
    if raw.get("created_at"):
        posted = datetime.fromtimestamp(raw["created_at"]).date()

    return JobRecord(
        source="vieclam24h",
        source_id=str(raw["id"]),
        title=raw.get("title") or "",
        company=employer.get("name"),
        location=location,
        salary_raw=salary_raw,
        level=str(raw["level_requirement"]) if raw.get("level_requirement") else None,
        job_type=str(raw["working_method"]) if raw.get("working_method") else None,
        description=html_to_text(raw.get("job_requirement")),
        requirements_raw=requirements,
        posted_date=posted,
        extra={
            "query": raw.get("_query"),
            "title_slug": raw.get("title_slug"),
            "occupation_ids": raw.get("occupation_ids_main"),
            "experience_range": raw.get("experience_range"),
        },
    )


def map_data_jobs(raw: dict) -> JobRecord:
    skills = _skill_list(raw.get("job_skills"))
    posted = None
    if raw.get("job_posted_date"):
        try:
            posted = date.fromisoformat(str(raw["job_posted_date"])[:10])
        except ValueError:
            posted = None
    salary = raw.get("salary_year_avg")

    return JobRecord(
        source="data_jobs",
        source_id=str(raw["_row_id"]),
        title=raw.get("job_title") or raw.get("job_title_short") or "",
        company=raw.get("company_name"),
        location=raw.get("job_location"),
        salary_raw=str(salary) if salary else None,
        job_type=raw.get("job_schedule_type"),
        requirements_raw=", ".join(skills) if skills else None,
        posted_date=posted,
        extra={
            "skills_given": skills,
            "job_title_short": raw.get("job_title_short"),
            "country": raw.get("job_country"),
        },
    )


def map_itviec(raw: dict) -> JobRecord:
    skills = raw.get("skills_ld") or raw.get("skills") or []
    posted = None
    if raw.get("date_posted"):
        try:
            posted = date.fromisoformat(str(raw["date_posted"])[:10])
        except ValueError:
            posted = None
    months = raw.get("months_experience")
    return JobRecord(
        source="itviec",
        source_id=str(raw.get("job_key") or raw.get("slug")),
        url=raw.get("url"),
        title=raw.get("title") or "",
        company=raw.get("company"),
        location=raw.get("location"),
        salary_raw=raw.get("salary_raw"),
        level=f"{months} months" if months else None,
        job_type=raw.get("employment_type"),
        description=raw.get("description"),
        requirements_raw=raw.get("requirements"),
        posted_date=posted,
        extra={
            "skills_given": skills,
            "slug": raw.get("slug"),
            "valid_through": raw.get("valid_through"),
            "industry": raw.get("industry"),
        },
    )


MAPPERS = {
    "vieclam24h": map_vieclam24h,
    "data_jobs": map_data_jobs,
    "itviec": map_itviec,
}


def suggest_field_matches(source_fields: list[str], threshold: int = 60) -> dict[str, str]:
    """Name-based matcher (slide 4-Part2): gợi ý khớp trường nguồn với trường mediated."""
    from rapidfuzz import fuzz, process

    targets = list(JobRecord.model_fields)
    result = {}
    for field in source_fields:
        match, score, _ = process.extractOne(field, targets, scorer=fuzz.WRatio)
        if score >= threshold:
            result[field] = match
    return result
