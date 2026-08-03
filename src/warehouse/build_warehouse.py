"""Nạp star schema vào DuckDB: dim_job/dim_company/dim_location/dim_time/dim_skill/
dim_skill_variant + fact_job_skill + bridge_skill_closure (thiết kế ở KE_HOACH_BTL.md
mục 3). Khoá chính dùng thẳng natural key (`record_id`, `skill_id`) thay vì sinh
surrogate int, vì các bảng nạp một lần từ file tĩnh, không cần slowly-changing dim.

salary_raw khác đơn vị theo nguồn (vieclam24h: khoảng lương tháng VNĐ; data_jobs:
lương trung bình năm USD) — tách min/max nhưng giữ nguyên `salary_currency`/
`salary_period` thay vì tự quy đổi tỷ giá (rủi ro sai số không kiểm chứng được).
"""

from __future__ import annotations

import json
import re

import duckdb
import pandas as pd

from src.common.paths import STAGING, WAREHOUSE_DB
from src.common.schema import norm_text

SALARY_META = {
    "vieclam24h": ("VND", "month"),
    "itviec": ("VND", "month"),
    "data_jobs": ("USD", "year"),
}


def _load_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _parse_salary(rec: dict) -> tuple[float | None, float | None]:
    raw = rec.get("salary_raw")
    if not raw:
        return None, None
    if rec["source"] == "data_jobs":
        try:
            value = float(raw)
        except ValueError:
            return None, None
        return value, value
    parts = raw.split("-")
    values = []
    for part in parts:
        try:
            values.append(float(part))
        except ValueError:
            values.append(None)
    values += [None] * (2 - len(values))
    return values[0], values[1]


def _guess_city(location: str | None) -> str | None:
    if not location:
        return None
    segments = [s.strip() for s in location.split(",") if s.strip()]
    return segments[-1] if segments else None


def _role_family(rec: dict) -> str | None:
    extra = rec.get("extra") or {}
    if rec["source"] == "data_jobs":
        return extra.get("job_title_short")
    if rec["source"] == "vieclam24h":
        return extra.get("query")
    return None


def _months_experience(level: str | None) -> int | None:
    if not level:
        return None
    match = re.match(r"(\d+)\s*months?", level)
    return int(match.group(1)) if match else None


def build_dim_company(records: list[dict]) -> pd.DataFrame:
    seen: dict[str, dict] = {}
    for rec in records:
        name = rec.get("company")
        if not name:
            continue
        key = norm_text(name)
        if key not in seen:
            seen[key] = {
                "company_id": len(seen) + 1,
                "name": name,
                "name_norm": key,
                "industry": (rec.get("extra") or {}).get("industry"),
            }
    return pd.DataFrame(seen.values())


def build_dim_location(records: list[dict]) -> pd.DataFrame:
    seen: dict[str, dict] = {}
    for rec in records:
        loc = rec.get("location")
        if not loc:
            continue
        key = norm_text(loc)
        if key not in seen:
            seen[key] = {
                "location_id": len(seen) + 1,
                "location_raw": loc,
                "city_guess": _guess_city(loc),
            }
    return pd.DataFrame(seen.values())


def build_dim_time(records: list[dict]) -> pd.DataFrame:
    seen: dict[str, dict] = {}
    for rec in records:
        date_str = rec.get("posted_date")
        if not date_str or date_str in seen:
            continue
        year, month, day = (int(p) for p in date_str.split("-"))
        seen[date_str] = {
            "date_id": date_str,
            "day": day,
            "month": month,
            "quarter": (month - 1) // 3 + 1,
            "year": year,
        }
    return pd.DataFrame(seen.values())


def build_dim_job(records: list[dict], company_ids: dict[str, int], location_ids: dict[str, int]) -> pd.DataFrame:
    rows = []
    for rec in records:
        smin, smax = _parse_salary(rec)
        currency, period = SALARY_META.get(rec["source"], (None, None))
        rows.append(
            {
                "job_id": f"{rec['source']}:{rec['source_id']}",
                "title_raw": rec.get("title"),
                "role_family": _role_family(rec),
                "company_id": company_ids.get(norm_text(rec.get("company"))),
                "location_id": location_ids.get(norm_text(rec.get("location"))),
                "level_raw": rec.get("level"),
                "months_experience": _months_experience(rec.get("level")),
                "salary_min": smin,
                "salary_max": smax,
                "salary_currency": currency if rec.get("salary_raw") else None,
                "salary_period": period if rec.get("salary_raw") else None,
                "job_type": rec.get("job_type"),
                "posted_date": rec.get("posted_date"),
                "source": rec["source"],
                "url": rec.get("url"),
            }
        )
    return pd.DataFrame(rows)


def build_dim_skill(skills: list[dict]) -> pd.DataFrame:
    by_id = {s["skill_id"]: s for s in skills}
    rows = []
    for s in skills:
        parent = by_id.get(s.get("parent_skill_id"))
        rows.append(
            {
                "skill_id": s["skill_id"],
                "canonical_name": s["canonical_name"],
                "skill_type": s["skill_type"],
                "category": parent["canonical_name"] if parent else None,
                "parent_skill_id": s.get("parent_skill_id"),
            }
        )
    return pd.DataFrame(rows)


def build_dim_skill_variant(skills: list[dict]) -> pd.DataFrame:
    rows = []
    variant_id = 1
    for s in skills:
        for surface_form in s["aliases"]:
            rows.append(
                {
                    "variant_id": variant_id,
                    "skill_id": s["skill_id"],
                    "surface_form": surface_form,
                }
            )
            variant_id += 1
    return pd.DataFrame(rows)


def build_fact_job_skill(job_skills: list[dict], valid_job_ids: set[str]) -> pd.DataFrame:
    rows = [
        {
            "job_id": m["record_id"],
            "skill_id": m["skill_id"],
            "skill_type": m["skill_type"],
            "source": m["source"],
            "extraction_method": m["method"],
            "confidence": m["score"],
            "evidence_snippet": m["evidence"],
        }
        for m in job_skills
        if m["record_id"] in valid_job_ids
    ]
    return pd.DataFrame(rows)


def build_bridge_closure(closure: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(closure)


def check_integrity(tables: dict[str, pd.DataFrame]) -> None:
    """Chặn việc nạp kho khi staging không nhất quán. Trước đây pipeline chạy lệch
    thứ tự vẫn nạp trót lọt: closure trỏ tới 17 skill_id không có trong dim_skill và
    toàn bộ phân cấp rỗng, nhưng không có chỗ nào báo lỗi."""
    skill_ids = set(tables["dim_skill"]["skill_id"])
    job_ids = set(tables["dim_job"]["job_id"])
    closure = tables["bridge_skill_closure"]
    fact = tables["fact_job_skill"]

    problems = []
    for label, missing in (
        ("fact_job_skill.skill_id", set(fact["skill_id"]) - skill_ids),
        ("fact_job_skill.job_id", set(fact["job_id"]) - job_ids),
        (
            "bridge_skill_closure",
            (set(closure["ancestor_id"]) | set(closure["descendant_id"])) - skill_ids,
        ),
        ("dim_skill.parent_skill_id", set(tables["dim_skill"]["parent_skill_id"].dropna()) - skill_ids),
    ):
        if missing:
            problems.append(f"{label}: {len(missing)} id lạ, ví dụ {sorted(missing)[:5]}")

    if not tables["dim_skill"]["parent_skill_id"].notna().any():
        problems.append("dim_skill.parent_skill_id rỗng hoàn toàn — thiếu bước build_hierarchy")

    if problems:
        raise ValueError("Staging không nhất quán:\n  " + "\n  ".join(problems))


def run() -> str:
    records = [r for r in _load_jsonl(STAGING / "records_deduped.jsonl") if r.get("is_canonical", True)]
    skills = json.loads((STAGING / "skill_dictionary.json").read_text(encoding="utf-8"))
    job_skills = _load_jsonl(STAGING / "job_skills.jsonl")
    closure = _load_jsonl(STAGING / "skill_closure.jsonl")

    dim_company = build_dim_company(records)
    dim_location = build_dim_location(records)
    dim_time = build_dim_time(records)
    company_ids = dict(zip(dim_company["name_norm"], dim_company["company_id"])) if not dim_company.empty else {}
    location_ids = (
        dict(zip(dim_location["location_raw"].map(norm_text), dim_location["location_id"]))
        if not dim_location.empty
        else {}
    )

    dim_job = build_dim_job(records, company_ids, location_ids)
    # Cột toàn NULL bị pandas suy thành float rồi DuckDB tạo cột INTEGER, khiến join
    # với skill_id (VARCHAR) báo lỗi kiểu thay vì trả kết quả rỗng.
    dim_skill = build_dim_skill(skills).astype({"category": "string", "parent_skill_id": "string"})
    dim_skill_variant = build_dim_skill_variant(skills)
    fact_job_skill = build_fact_job_skill(job_skills, set(dim_job["job_id"]))
    bridge_skill_closure = build_bridge_closure(closure)

    tables = {
        "dim_company": dim_company,
        "dim_location": dim_location,
        "dim_time": dim_time,
        "dim_job": dim_job,
        "dim_skill": dim_skill,
        "dim_skill_variant": dim_skill_variant,
        "fact_job_skill": fact_job_skill,
        "bridge_skill_closure": bridge_skill_closure,
    }
    check_integrity(tables)

    WAREHOUSE_DB.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = duckdb.connect(str(WAREHOUSE_DB))
    except duckdb.IOException as exc:
        # DuckDB chỉ cho một tiến trình mở file, kể cả tiến trình kia mở read-only.
        raise SystemExit(
            f"Không mở được {WAREHOUSE_DB} để ghi. Hãy tắt API/Streamlit đang chạy rồi thử lại.\n{exc}"
        ) from exc
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()

    for name, df in tables.items():
        print(f"{name}: {len(df)} dòng")
    print(f"Warehouse -> {WAREHOUSE_DB}")
    return str(WAREHOUSE_DB)


if __name__ == "__main__":
    run()
