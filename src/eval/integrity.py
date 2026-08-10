"""Kiểm tra ràng buộc trên kho đã nạp.

Khác với `check_integrity` trong build_warehouse (chạy trên DataFrame, chặn việc nạp
kho lệch), phần này chạy trên file DuckDB thật để báo cáo trạng thái kho hiện có —
kể cả khi kho được nạp bởi một lượt chạy cũ.
"""

from __future__ import annotations

import duckdb

from src.common.schema import strip_accents
from src.process.skill_dictionary import _slugify

Check = tuple[str, bool, str]

FOREIGN_KEYS = [
    ("job_skills.skill_id", "job_skills", "skill_id", "skills", "skill_id"),
    ("job_skills.job_id", "job_skills", "job_id", "jobs", "job_id"),
    ("skill_closure.ancestor_id", "skill_closure", "ancestor_id", "skills", "skill_id"),
    ("skill_closure.descendant_id", "skill_closure", "descendant_id", "skills", "skill_id"),
    ("skills.parent_skill_id", "skills", "parent_skill_id", "skills", "skill_id"),
    ("skill_terms.skill_id", "skill_terms", "skill_id", "skills", "skill_id"),
    ("skill_variants.skill_id", "skill_variants", "skill_id", "skills", "skill_id"),
    ("jobs.company_id", "jobs", "company_id", "companies", "company_id"),
    ("jobs.location_id", "jobs", "location_id", "locations", "location_id"),
]


def _orphans(con: duckdb.DuckDBPyConnection, table: str, column: str, ref_table: str, ref_column: str) -> int:
    sql = f"""
        SELECT count(*) FROM {table}
        WHERE {column} IS NOT NULL
          AND {column} NOT IN (SELECT {ref_column} FROM {ref_table} WHERE {ref_column} IS NOT NULL)
    """
    return con.execute(sql).fetchone()[0]


def run_checks(con: duckdb.DuckDBPyConnection) -> list[Check]:
    checks: list[Check] = []

    for label, table, column, ref_table, ref_column in FOREIGN_KEYS:
        n = _orphans(con, table, column, ref_table, ref_column)
        checks.append((f"FK {label} -> {ref_table}", n == 0, f"{n} giá trị không tham chiếu được"))

    n_skills = con.execute("SELECT count(*) FROM skills").fetchone()[0]
    n_self = con.execute("SELECT count(*) FROM skill_closure WHERE depth = 0").fetchone()[0]
    checks.append(("Closure có dòng self cho mọi skill", n_self == n_skills, f"{n_self}/{n_skills}"))

    max_depth = con.execute("SELECT max(depth) FROM skill_closure").fetchone()[0] or 0
    checks.append(("Closure bắc cầu quá một mức", max_depth >= 2, f"độ sâu tối đa {max_depth}"))

    n_parent = con.execute("SELECT count(*) FROM skills WHERE parent_skill_id IS NOT NULL").fetchone()[0]
    checks.append(("Phân cấp không rỗng", n_parent > 0, f"{n_parent}/{n_skills} skill có cha"))

    unreachable = con.execute("""
        SELECT count(*) FROM skills s
        WHERE NOT EXISTS (
            SELECT 1 FROM skill_closure c
            WHERE c.descendant_id = s.skill_id AND c.depth = 0
        )
        """).fetchone()[0]
    checks.append(("Mọi skill đều tra được qua closure", unreachable == 0, f"{unreachable} skill thiếu"))

    leaked = con.execute("""
        SELECT count(*) FROM job_skills f
        JOIN skills s ON s.skill_id = f.skill_id
        WHERE s.is_category
        """).fetchone()[0]
    checks.append(
        ("Nút nhóm không bị trích chọn như kỹ năng thường", leaked == 0, f"{leaked} cặp")
    )

    no_term = con.execute("""
        SELECT count(*) FROM skills s
        WHERE NOT EXISTS (SELECT 1 FROM skill_terms t WHERE t.skill_id = s.skill_id)
        """).fetchone()[0]
    checks.append(("Mọi skill đều có từ khoá tìm kiếm", no_term == 0, f"{no_term} skill thiếu"))

    # So bằng hàm bỏ dấu của hệ thống, không dùng strip_accents của DuckDB: hàm đó
    # không xử lý "đ" nên "Đọc bản vẽ" sẽ bị báo lỗi oan.
    terms_by_skill: dict[str, set[str]] = {}
    for skill_id, term in con.execute("SELECT skill_id, term FROM skill_terms").fetchall():
        terms_by_skill.setdefault(skill_id, set()).add(term)
    missing_ascii = [
        skill_id
        for skill_id, name in con.execute("SELECT skill_id, canonical_name FROM skills").fetchall()
        if strip_accents(name) not in terms_by_skill.get(skill_id, set())
    ]
    checks.append(
        (
            "Kỹ năng có dấu đều tra được bằng chuỗi không dấu",
            not missing_ascii,
            f"{len(missing_ascii)} skill thiếu, ví dụ {missing_ascii[:5]}",
        )
    )

    lossy = con.execute("SELECT skill_id, canonical_name FROM skills").fetchall()
    mismatch = [sid for sid, name in lossy if _slugify(name) != sid]
    checks.append(
        (
            "skill_id khớp slug của canonical_name",
            not mismatch,
            f"{len(mismatch)} lệch, ví dụ {mismatch[:5]}",
        )
    )

    empty_columns = []
    for table in ("skills", "jobs"):
        for (column,) in con.execute(f"SELECT column_name FROM (DESCRIBE {table})").fetchall():
            filled = con.execute(f"SELECT count({column}) FROM {table}").fetchone()[0]
            if filled == 0:
                empty_columns.append(f"{table}.{column}")
    checks.append(("Không có cột chính rỗng hoàn toàn", not empty_columns, ", ".join(empty_columns)))

    return checks
