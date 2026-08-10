import duckdb
import pytest

from src.eval.integrity import run_checks


def _warehouse(parent_of_python: str | None = "lang", closure_extra: str = "") -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE skills (skill_id VARCHAR, canonical_name VARCHAR, skill_type VARCHAR, "
        "category VARCHAR, parent_skill_id VARCHAR, is_category BOOLEAN)"
    )
    con.execute(f"""
        INSERT INTO skills VALUES
            ('it', 'it', 'hard', NULL, NULL, true),
            ('lang', 'lang', 'hard', 'it', 'it', true),
            ('python', 'Python', 'hard', 'lang',
             {'NULL' if parent_of_python is None else f"'{parent_of_python}'"}, false)
        """)
    con.execute("CREATE TABLE skill_terms (skill_id VARCHAR, term VARCHAR)")
    con.execute("INSERT INTO skill_terms VALUES ('it', 'it'), ('lang', 'lang'), ('python', 'python')")
    con.execute("CREATE TABLE skill_variants (variant_id INTEGER, skill_id VARCHAR, surface_form VARCHAR)")
    con.execute("INSERT INTO skill_variants VALUES (1, 'python', 'python')")
    con.execute("CREATE TABLE companies (company_id INTEGER, name VARCHAR, name_norm VARCHAR, industry VARCHAR)")
    con.execute("INSERT INTO companies VALUES (1, 'ACME', 'acme', NULL)")
    con.execute("CREATE TABLE locations (location_id INTEGER, location_raw VARCHAR, city VARCHAR, country VARCHAR)")
    con.execute("INSERT INTO locations VALUES (1, 'Ha Noi', 'Hà Nội', 'Việt Nam')")
    con.execute(
        "CREATE TABLE jobs (job_id VARCHAR, title_raw VARCHAR, company_id INTEGER, location_id INTEGER, "
        "posted_date VARCHAR, source VARCHAR, seniority VARCHAR)"
    )
    con.execute("INSERT INTO jobs VALUES ('j1', 'Dev', 1, 1, '2026-01-01', 'itviec', 'Cao cấp')")
    con.execute(
        "CREATE TABLE job_skills (job_id VARCHAR, skill_id VARCHAR, skill_type VARCHAR, source VARCHAR, "
        "extraction_method VARCHAR, confidence DOUBLE, evidence_snippet VARCHAR)"
    )
    con.execute("INSERT INTO job_skills VALUES ('j1', 'python', 'hard', 'itviec', 'exact_match', 100, 'Python')")
    con.execute("CREATE TABLE skill_closure (ancestor_id VARCHAR, descendant_id VARCHAR, depth INTEGER)")
    con.execute(f"""
        INSERT INTO skill_closure VALUES
            ('it', 'it', 0), ('lang', 'lang', 0), ('python', 'python', 0),
            ('it', 'lang', 1), ('lang', 'python', 1), ('it', 'python', 2)
            {closure_extra}
        """)
    return con


def _failed(checks):
    return [label for label, ok, _ in checks if not ok]


def test_consistent_warehouse_passes_every_check():
    assert _failed(run_checks(_warehouse())) == []


def test_closure_referencing_unknown_skill_is_reported():
    checks = run_checks(_warehouse(closure_extra=", ('it', 'ghost', 1)"))
    assert any("skill_closure.descendant_id" in label for label in _failed(checks))


def test_flat_hierarchy_is_reported():
    con = _warehouse()
    con.execute("UPDATE skills SET parent_skill_id = NULL")
    con.execute("DELETE FROM skill_closure WHERE depth > 0")
    failed = _failed(run_checks(con))
    assert "Phân cấp không rỗng" in failed
    assert "Closure bắc cầu quá một mức" in failed


def test_lossy_skill_id_is_reported():
    con = _warehouse()
    con.execute("UPDATE skills SET canonical_name = 'C#' WHERE skill_id = 'python'")
    assert "skill_id khớp slug của canonical_name" in _failed(run_checks(con))


def test_fact_on_category_node_is_reported():
    con = _warehouse()
    con.execute("INSERT INTO job_skills VALUES ('j1', 'lang', 'hard', 'itviec', 'exact_match', 100, 'lang')")
    assert "Nút nhóm không bị trích chọn như kỹ năng thường" in _failed(run_checks(con))


def test_missing_accentless_term_is_reported():
    con = _warehouse()
    con.execute("UPDATE skills SET canonical_name = 'Tiếng Anh' WHERE skill_id = 'python'")
    assert "Kỹ năng có dấu đều tra được bằng chuỗi không dấu" in _failed(run_checks(con))


@pytest.mark.parametrize("column", ["category", "parent_skill_id"])
def test_empty_dimension_column_is_reported(column):
    con = _warehouse()
    con.execute(f"UPDATE skills SET {column} = NULL")
    assert "Không có cột chính rỗng hoàn toàn" in _failed(run_checks(con))
