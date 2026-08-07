"""Nạp star schema vào DuckDB: dim_job/dim_company/dim_location/dim_time/dim_skill/
dim_skill_variant/dim_skill_term + fact_job_skill + bridge_skill_closure. Khoá chính
dùng thẳng natural key (`record_id`, `skill_id`) thay vì sinh surrogate int, vì các
bảng nạp một lần từ file tĩnh, không cần slowly-changing dim.

Các chiều nhóm nghề, địa điểm, cấp bậc và lương được đưa về từ vựng chung ở
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


def _load_jsonl(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _location_key(rec: dict) -> str | None:
    """Khoá tự nhiên của dim_location: địa chỉ thô ghép mã tỉnh.

    vieclam24h cắt ngắn địa chỉ nên hai tin ở hai tỉnh vẫn có thể trùng chuỗi ("Tại
    công trình dự án"); chỉ khoá theo địa chỉ thì chúng gộp thành một dòng và một
    trong hai tin bị gán sai tỉnh.
    """
    location = rec.get("location")
    if not location:
        return None
    province_id = (rec.get("extra") or {}).get("province_id")
    return f"{norm_text(location)}|{province_id if province_id is not None else ''}"


def _role_hint(rec: dict) -> str | None:
    extra = rec.get("extra") or {}
    return extra.get("job_title_short") or extra.get("query")


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


def build_dim_location(records: list[dict]) -> tuple[pd.DataFrame, dict[str, int]]:
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
        smin, smax, currency, period = normalize.salary(rec.get("salary_raw"), rec["source"])
        months = normalize.months_experience(rec.get("level"))
        rows.append(
            {
                "job_id": f"{rec['source']}:{rec['source_id']}",
                "title_raw": rec.get("title"),
                "role_family": normalize.role_family(rec.get("title"), _role_hint(rec)),
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
                "is_category": bool(s.get("is_category")),
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


def search_terms(skill: dict) -> set[str]:
    """Các dạng viết dùng để đối sánh truy vấn: nguyên bản, bỏ dấu, bỏ luôn khoảng trắng.

    Tách khỏi `dim_skill_variant` vì bảng đó còn dùng để hiển thị cho người dùng xem
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


def build_dim_skill_term(skills: list[dict]) -> pd.DataFrame:
    rows = [
        {"skill_id": s["skill_id"], "term": term}
        for s in skills
        for term in sorted(search_terms(s))
    ]
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
        ("dim_skill_term.skill_id", set(tables["dim_skill_term"]["skill_id"]) - skill_ids),
    ):
        if missing:
            problems.append(f"{label}: {len(missing)} id lạ, ví dụ {sorted(missing)[:5]}")

    if not tables["dim_skill"]["parent_skill_id"].notna().any():
        problems.append("dim_skill.parent_skill_id rỗng hoàn toàn — thiếu bước build_hierarchy")

    invented = set(tables["dim_skill"].loc[tables["dim_skill"]["is_category"], "skill_id"])
    leaked = invented & set(fact["skill_id"])
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

    dim_company = build_dim_company(records)
    dim_location, location_ids = build_dim_location(records)
    dim_time = build_dim_time(records)
    company_ids = dict(zip(dim_company["name_norm"], dim_company["company_id"])) if not dim_company.empty else {}

    dim_job = build_dim_job(records, company_ids, location_ids)
    # Cột toàn NULL bị pandas suy thành float rồi DuckDB tạo cột INTEGER, khiến join
    # với skill_id (VARCHAR) báo lỗi kiểu thay vì trả kết quả rỗng.
    dim_skill = build_dim_skill(skills).astype({"category": "string", "parent_skill_id": "string"})
    dim_skill_variant = build_dim_skill_variant(skills)
    dim_skill_term = build_dim_skill_term(skills)
    fact_job_skill = build_fact_job_skill(job_skills, set(dim_job["job_id"]))
    bridge_skill_closure = build_bridge_closure(closure)

    tables = {
        "dim_company": dim_company,
        "dim_location": dim_location,
        "dim_time": dim_time,
        "dim_job": dim_job,
        "dim_skill": dim_skill,
        "dim_skill_variant": dim_skill_variant,
        "dim_skill_term": dim_skill_term,
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
