"""Lớp truy vấn trên kho DuckDB — dùng chung cho FastAPI (`src/api/main.py`) và
Streamlit (`src/app/streamlit_app.py`) để tránh viết SQL lặp ở hai nơi.

Mỗi hàm nhận `con` (duckdb connection) làm tham số đầu để test được với một kho
DuckDB tạm dựng từ dữ liệu mẫu, không phụ thuộc `data/warehouse.duckdb` thật.
"""

from __future__ import annotations

from urllib.parse import quote_plus

import duckdb

from src.common.paths import WAREHOUSE_DB
from src.common.schema import strip_accents


def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(WAREHOUSE_DB), read_only=read_only)


def _escape_like(value: str) -> str:
    """Chặn ký tự đại diện của LIKE lọt từ truy vấn người dùng vào mẫu đối sánh."""
    for char in ("\\", "%", "_"):
        value = value.replace(char, "\\" + char)
    return value


def search_skills(con: duckdb.DuckDBPyConnection, query: str, limit: int = 20) -> list[dict]:
    """Tìm kỹ năng theo chuỗi người dùng gõ, không phân biệt dấu và có xếp hạng.

    Đối sánh chạy trên `dim_skill_term` (đã bỏ dấu và có dạng dính liền) nên "tieng
    anh" ra "Tiếng Anh" và "next js" ra "NextJS". Thứ tự trả về ưu tiên khớp đúng cả
    chuỗi, rồi khớp tiền tố, rồi tên ngắn hơn — nếu chỉ ORDER BY tên thì truy vấn
    "sql" trả về MySQL, NoSQL, PostgreSQL trước chính SQL.
    """
    term = " ".join(strip_accents(query).split())
    if not term:
        return []
    compact = term.replace(" ", "")
    escaped, escaped_compact = _escape_like(term), _escape_like(compact)

    sql = """
        SELECT s.skill_id, s.canonical_name, s.skill_type, s.category,
               max(CASE
                     WHEN t.term IN (?, ?) THEN 3
                     WHEN t.term LIKE ? ESCAPE '\\' OR t.term LIKE ? ESCAPE '\\' THEN 2
                     ELSE 1
                   END) AS match_rank
        FROM dim_skill s
        JOIN dim_skill_term t ON t.skill_id = s.skill_id
        WHERE t.term LIKE ? ESCAPE '\\' OR t.term LIKE ? ESCAPE '\\'
        GROUP BY s.skill_id, s.canonical_name, s.skill_type, s.category
        ORDER BY match_rank DESC, length(s.canonical_name), s.canonical_name
        LIMIT ?
    """
    params = [
        term, compact,
        f"{escaped}%", f"{escaped_compact}%",
        f"%{escaped}%", f"%{escaped_compact}%",
        limit,
    ]
    rows = con.execute(sql, params).fetchdf().to_dict("records")
    for row in rows:
        row.pop("match_rank", None)
    return rows


def get_skill_detail(con: duckdb.DuckDBPyConnection, skill_id: str) -> dict | None:
    base = con.execute("SELECT * FROM dim_skill WHERE skill_id = ?", [skill_id]).fetchdf()
    if base.empty:
        return None
    info = base.iloc[0].to_dict()

    parent = None
    if info.get("parent_skill_id"):
        prow = con.execute(
            "SELECT skill_id, canonical_name FROM dim_skill WHERE skill_id = ?",
            [info["parent_skill_id"]],
        ).fetchdf()
        if not prow.empty:
            parent = prow.iloc[0].to_dict()

    children = con.execute(
        "SELECT skill_id, canonical_name FROM dim_skill WHERE parent_skill_id = ? ORDER BY canonical_name",
        [skill_id],
    ).fetchdf().to_dict("records")

    variants = con.execute(
        "SELECT surface_form FROM dim_skill_variant WHERE skill_id = ? ORDER BY surface_form",
        [skill_id],
    ).fetchdf()["surface_form"].tolist()

    job_count = con.execute(
        "SELECT count(DISTINCT job_id) FROM fact_job_skill WHERE skill_id = ?", [skill_id]
    ).fetchone()[0]

    evidence = con.execute(
        """
        SELECT source, extraction_method, confidence, evidence_snippet
        FROM fact_job_skill WHERE skill_id = ?
        ORDER BY confidence DESC LIMIT 5
        """,
        [skill_id],
    ).fetchdf().to_dict("records")

    return {
        "skill_id": info["skill_id"],
        "canonical_name": info["canonical_name"],
        "skill_type": info["skill_type"],
        "parent": parent,
        "children": children,
        "variants": variants,
        "job_count": job_count,
        "evidence_samples": evidence,
    }


def expand_skill_ids(con: duckdb.DuckDBPyConnection, skill_id: str) -> list[str]:
    rows = con.execute(
        "SELECT descendant_id FROM bridge_skill_closure WHERE ancestor_id = ?", [skill_id]
    ).fetchdf()
    ids = rows["descendant_id"].tolist()
    return ids or [skill_id]


def search_jobs(
    con: duckdb.DuckDBPyConnection,
    skill_id: str,
    expand: bool = True,
    skill_type: str | None = None,
    role_family: str | None = None,
    city: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    skill_ids = expand_skill_ids(con, skill_id) if expand else [skill_id]
    placeholders = ",".join(["?"] * len(skill_ids))
    filters = [f"f.skill_id IN ({placeholders})"]
    params: list = list(skill_ids)

    if skill_type:
        filters.append("f.skill_type = ?")
        params.append(skill_type)
    if role_family:
        filters.append("j.role_family = ?")
        params.append(role_family)
    if city:
        filters.append("l.city = ?")
        params.append(city)

    where = " AND ".join(filters)
    sql = f"""
        SELECT j.job_id, j.title_raw, c.name AS company, l.location_raw AS location,
               l.city, j.source, j.url, j.posted_date, j.seniority,
               string_agg(DISTINCT sk.canonical_name, ', ') AS matched_skills
        FROM fact_job_skill f
        JOIN dim_job j ON j.job_id = f.job_id
        JOIN dim_skill sk ON sk.skill_id = f.skill_id
        LEFT JOIN dim_company c ON c.company_id = j.company_id
        LEFT JOIN dim_location l ON l.location_id = j.location_id
        WHERE {where}
        GROUP BY j.job_id, j.title_raw, c.name, l.location_raw, l.city, j.source,
                 j.url, j.posted_date, j.seniority
        ORDER BY j.posted_date DESC NULLS LAST
        LIMIT ? OFFSET ?
    """
    params += [limit, offset]
    rows = con.execute(sql, params).fetchdf().to_dict("records")
    for row in rows:
        row["source_search_url"] = source_search_url(row["source"], row["title_raw"])
    return rows


# Chỉ itviec trả về đường dẫn tin trong dữ liệu; hai nguồn còn lại không phát hành
# URL chi tiết (vieclam24h render phía trình duyệt, data_jobs là bản trích từ Google
# Jobs không kèm link). Không đoán đường dẫn, chỉ đưa người dùng về trang tìm kiếm
# của nguồn để tự đối chiếu.
SOURCE_SEARCH = {
    "vieclam24h": "https://vieclam24h.vn/tim-kiem-viec-lam-nhanh?q={q}",
    "itviec": "https://itviec.com/it-jobs?query={q}",
}


def source_search_url(source: str, title: str | None) -> str | None:
    template = SOURCE_SEARCH.get(source)
    if not template or not title:
        return None
    return template.format(q=quote_plus(title))


def top_skills(
    con: duckdb.DuckDBPyConnection,
    skill_type: str | None = None,
    role_family: str | None = None,
    city: str | None = None,
    limit: int = 20,
) -> list[dict]:
    filters = []
    params: list = []
    if skill_type:
        filters.append("s.skill_type = ?")
        params.append(skill_type)
    if role_family:
        filters.append("j.role_family = ?")
        params.append(role_family)
    if city:
        filters.append("l.city = ?")
        params.append(city)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    sql = f"""
        SELECT s.canonical_name, s.category, s.skill_type, count(DISTINCT f.job_id) AS n
        FROM fact_job_skill f
        JOIN dim_skill s ON s.skill_id = f.skill_id
        JOIN dim_job j ON j.job_id = f.job_id
        LEFT JOIN dim_location l ON l.location_id = j.location_id
        {where}
        GROUP BY s.canonical_name, s.category, s.skill_type
        ORDER BY n DESC
        LIMIT ?
    """
    params.append(limit)
    return con.execute(sql, params).fetchdf().to_dict("records")


def hard_soft_ratio(con: duckdb.DuckDBPyConnection, role_family: str | None = None) -> dict[str, int]:
    """Số tin có yêu cầu kỹ năng cứng / kỹ năng mềm.

    Đếm theo tin chứ không theo dòng fact để cùng đơn vị với `top_skills`; một tin đòi
    cả hai loại thì được tính ở cả hai nhóm.
    """
    filters = []
    params: list = []
    if role_family:
        filters.append("j.role_family = ?")
        params.append(role_family)
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    sql = f"""
        SELECT s.skill_type, count(DISTINCT f.job_id) AS n
        FROM fact_job_skill f
        JOIN dim_skill s ON s.skill_id = f.skill_id
        JOIN dim_job j ON j.job_id = f.job_id
        {where}
        GROUP BY s.skill_type
    """
    rows = con.execute(sql, params).fetchdf().to_dict("records")
    return {row["skill_type"]: row["n"] for row in rows}


def list_role_families(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT role_family FROM dim_job WHERE role_family IS NOT NULL ORDER BY role_family"
    ).fetchdf()
    return rows["role_family"].tolist()


def list_cities(con: duckdb.DuckDBPyConnection, min_jobs: int = 5) -> list[str]:
    """Các thành phố đủ số tin để lọc có nghĩa, xếp theo số tin giảm dần.

    Trả về toàn bộ giá trị phân biệt thì danh sách dài hàng nghìn dòng và hơn nửa chỉ
    ứng với đúng một tin, không dùng được làm bộ lọc.
    """
    rows = con.execute(
        """
        SELECT l.city, count(*) AS n
        FROM dim_job j
        JOIN dim_location l ON l.location_id = j.location_id
        WHERE l.city IS NOT NULL
        GROUP BY l.city
        HAVING count(*) >= ?
        ORDER BY n DESC, l.city
        """,
        [min_jobs],
    ).fetchdf()
    return rows["city"].tolist()
