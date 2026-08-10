"""Nạp dữ liệu tích hợp vào các bảng quan hệ trong DuckDB.

Lược đồ gồm jobs/companies/locations, skills/skill_variants/skill_terms,
job_skills và skill_closure. Ngày đăng là thuộc tính của jobs; cây kỹ năng được
biểu diễn bằng skills.parent_skill_id, còn skill_closure là quan hệ dẫn xuất để
truy vấn tổ tiên và hậu duệ.

Địa điểm, cấp bậc và lương được đưa về từ vựng chung ở
`src.integration.normalize` chứ không giữ nguyên giá trị nguồn; lương thì tách số và
suy đơn vị nhưng không quy đổi tỷ giá (rủi ro sai số không kiểm chứng được).
"""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.common.paths import STAGING, WAREHOUSE_DB
from src.common.schema import norm_text, strip_accents
from src.integration import normalize

LEGACY_TABLES = (
    "dim_company",
    "dim_location",
    "dim_time",
    "dim_job",
    "dim_skill",
    "dim_skill_variant",
    "dim_skill_term",
    "fact_job_skill",
    "bridge_skill_closure",
)


def _load_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _location_key(rec: dict) -> str | None:
    """Khoá đối chiếu địa điểm: địa chỉ thô ghép mã tỉnh.

    vieclam24h cắt ngắn địa chỉ nên hai tin ở hai tỉnh vẫn có thể trùng chuỗi ("Tại
    công trình dự án"); chỉ khoá theo địa chỉ thì chúng gộp thành một dòng và một
    trong hai tin bị gán sai tỉnh.
    """
    location = rec.get("location")
    if not location:
        return None
    province_id = (rec.get("extra") or {}).get("province_id")
    return f"{norm_text(location)}|{province_id if province_id is not None else ''}"


def build_companies(records: list[dict]) -> pd.DataFrame:
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


def build_locations(records: list[dict]) -> tuple[pd.DataFrame, dict[str, int]]:
    seen: dict[str, dict] = {}
    for rec in records:
        key = _location_key(rec)
        if key is None or key in seen:
            continue
        extra = rec.get("extra") or {}
        city, country = normalize.city_country(
            rec["location"],
            rec["source"],
            extra.get("country"),
            province_id=extra.get("province_id"),
            address_hint=extra.get("contact_address"),
        )
        seen[key] = {
            "location_id": len(seen) + 1,
            "location_raw": rec["location"],
            "city": city,
            "country": country,
        }
    ids = {key: row["location_id"] for key, row in seen.items()}
    return pd.DataFrame(seen.values()), ids


def build_jobs(records: list[dict], company_ids: dict[str, int], location_ids: dict[str, int]) -> pd.DataFrame:
    rows = []
    for rec in records:
        smin, smax, currency, period = normalize.salary(rec.get("salary_raw"), rec["source"])
        months = normalize.months_experience(rec.get("level"))
        rows.append(
            {
                "job_id": f"{rec['source']}:{rec['source_id']}",
                "title_raw": rec.get("title"),
                "company_id": company_ids.get(norm_text(rec.get("company"))),
                "location_id": location_ids.get(_location_key(rec)),
                "level_raw": rec.get("level"),
                "seniority": normalize.seniority(rec.get("title"), months),
                "months_experience": months,
                "salary_min": smin,
                "salary_max": smax,
                "salary_currency": currency,
                "salary_period": period,
                "job_type": rec.get("job_type"),
                "posted_date": rec.get("posted_date"),
                "source": rec["source"],
                "url": rec.get("url"),
            }
        )
    return pd.DataFrame(rows)


def build_skills(skills: list[dict]) -> pd.DataFrame:
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
                "is_category": bool(s.get("is_category")),
            }
        )
    return pd.DataFrame(rows)


def build_skill_variants(skills: list[dict]) -> pd.DataFrame:
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


def search_terms(skill: dict) -> set[str]:
    """Các dạng viết dùng để đối sánh truy vấn: nguyên bản, bỏ dấu, bỏ luôn khoảng trắng.

    Tách khỏi `skill_variants` vì bảng đó còn dùng để hiển thị cho người dùng xem
    các biến thể đã gộp; nhét thêm dạng bỏ dấu và dạng dính liền vào đó thì trang tra
    cứu kỹ năng đầy chuỗi rác.
    """
    terms: set[str] = set()
    for form in [skill["canonical_name"], *skill["aliases"]]:
        folded = " ".join(form.lower().split())
        for term in (folded, strip_accents(folded)):
            if not term:
                continue
            terms.add(term)
            compact = term.replace(" ", "")
            if compact:
                terms.add(compact)
    return terms


def build_skill_terms(skills: list[dict]) -> pd.DataFrame:
    rows = [
        {"skill_id": s["skill_id"], "term": term}
        for s in skills
        for term in sorted(search_terms(s))
    ]
    return pd.DataFrame(rows)


def build_job_skills(job_skills: list[dict], valid_job_ids: set[str]) -> pd.DataFrame:
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


def build_skill_closure(closure: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(closure)


def check_integrity(tables: dict[str, pd.DataFrame]) -> None:
    """Chặn việc nạp kho khi staging không nhất quán. Trước đây pipeline chạy lệch
    thứ tự vẫn nạp trót lọt: closure trỏ tới skill_id không có trong skills và
    toàn bộ phân cấp rỗng, nhưng không có chỗ nào báo lỗi."""
    skill_ids = set(tables["skills"]["skill_id"])
    job_ids = set(tables["jobs"]["job_id"])
    closure = tables["skill_closure"]
    pairs = tables["job_skills"]

    problems = []
    for label, missing in (
        ("job_skills.skill_id", set(pairs["skill_id"]) - skill_ids),
        ("job_skills.job_id", set(pairs["job_id"]) - job_ids),
        (
            "skill_closure",
            (set(closure["ancestor_id"]) | set(closure["descendant_id"])) - skill_ids,
        ),
        ("skills.parent_skill_id", set(tables["skills"]["parent_skill_id"].dropna()) - skill_ids),
        ("skill_terms.skill_id", set(tables["skill_terms"]["skill_id"]) - skill_ids),
    ):
        if missing:
            problems.append(f"{label}: {len(missing)} id lạ, ví dụ {sorted(missing)[:5]}")

    if not tables["skills"]["parent_skill_id"].notna().any():
        problems.append("skills.parent_skill_id rỗng hoàn toàn — thiếu bước build_hierarchy")

    invented = set(tables["skills"].loc[tables["skills"]["is_category"], "skill_id"])
    leaked = invented & set(pairs["skill_id"])
    if leaked:
        problems.append(
            f"nút nhóm bị trích chọn như kỹ năng thường: {sorted(leaked)[:5]} "
            "— dấu hiệu bước trích chọn chạy trên từ điển đã gắn phân cấp"
        )

    if problems:
        raise ValueError("Staging không nhất quán:\n  " + "\n  ".join(problems))


def run() -> str:
    records = [r for r in _load_jsonl(STAGING / "records_deduped.jsonl") if r.get("is_canonical", True)]
    skills = json.loads((STAGING / "skill_dictionary.json").read_text(encoding="utf-8"))
    job_skills = _load_jsonl(STAGING / "job_skills.jsonl")
    closure = _load_jsonl(STAGING / "skill_closure.jsonl")

    companies = build_companies(records)
    locations, location_ids = build_locations(records)
    company_ids = dict(zip(companies["name_norm"], companies["company_id"])) if not companies.empty else {}

    jobs = build_jobs(records, company_ids, location_ids)
    # Cột toàn NULL bị pandas suy thành float rồi DuckDB tạo cột INTEGER, khiến join
    # với skill_id (VARCHAR) báo lỗi kiểu thay vì trả kết quả rỗng.
    skills_table = build_skills(skills).astype({"category": "string", "parent_skill_id": "string"})
    skill_variants = build_skill_variants(skills)
    skill_terms = build_skill_terms(skills)
    job_skill_pairs = build_job_skills(job_skills, set(jobs["job_id"]))
    skill_closure = build_skill_closure(closure)

    tables = {
        "companies": companies,
        "locations": locations,
        "jobs": jobs,
        "skills": skills_table,
        "skill_variants": skill_variants,
        "skill_terms": skill_terms,
        "job_skills": job_skill_pairs,
        "skill_closure": skill_closure,
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
    for name in LEGACY_TABLES:
        con.execute(f"DROP TABLE IF EXISTS {name}")
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()

    for name, df in tables.items():
        print(f"{name}: {len(df)} dòng")
    print(f"Database -> {WAREHOUSE_DB}")
    return str(WAREHOUSE_DB)


if __name__ == "__main__":
    run()
