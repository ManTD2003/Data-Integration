"""FastAPI cho công cụ tìm kiếm: tìm việc theo kỹ năng (mở rộng phân cấp), tra cứu
kỹ năng (provenance), thống kê OLAP. Chạy: `uvicorn src.api.main:app --reload`.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from src.api import queries

app = FastAPI(title="Tích hợp kỹ năng tuyển dụng")


@app.get("/skills")
def api_search_skills(q: str = Query(..., min_length=1), limit: int = 20):
    con = queries.get_connection()
    try:
        return queries.search_skills(con, q, limit)
    finally:
        con.close()


@app.get("/skills/{skill_id}")
def api_skill_detail(skill_id: str):
    con = queries.get_connection()
    try:
        detail = queries.get_skill_detail(con, skill_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy kỹ năng")
        return detail
    finally:
        con.close()


@app.get("/jobs/search")
def api_search_jobs(
    skill_id: str,
    expand: bool = True,
    skill_type: str | None = None,
    role_family: str | None = None,
    city: str | None = None,
    country: str | None = None,
    limit: int = 20,
    offset: int = 0,
):
    con = queries.get_connection()
    try:
        return queries.search_jobs(
            con, skill_id, expand=expand, skill_type=skill_type, role_family=role_family,
            city=city, country=country, limit=limit, offset=offset,
        )
    finally:
        con.close()


@app.get("/stats/top-skills")
def api_top_skills(
    skill_type: str | None = None,
    role_family: str | None = None,
    city: str | None = None,
    limit: int = 20,
):
    con = queries.get_connection()
    try:
        return queries.top_skills(con, skill_type=skill_type, role_family=role_family, city=city, limit=limit)
    finally:
        con.close()


@app.get("/stats/hard-soft-ratio")
def api_hard_soft_ratio(role_family: str | None = None):
    con = queries.get_connection()
    try:
        return queries.hard_soft_ratio(con, role_family=role_family)
    finally:
        con.close()


@app.get("/filters/role-families")
def api_role_families():
    con = queries.get_connection()
    try:
        return queries.list_role_families(con)
    finally:
        con.close()


@app.get("/filters/countries")
def api_countries(min_jobs: int = 5):
    con = queries.get_connection()
    try:
        return queries.list_countries(con, min_jobs=min_jobs)
    finally:
        con.close()


@app.get("/filters/cities")
def api_cities(country: str | None = None, min_jobs: int = 5):
    con = queries.get_connection()
    try:
        return queries.list_cities(con, country=country, min_jobs=min_jobs)
    finally:
        con.close()
