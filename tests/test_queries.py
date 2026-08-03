import duckdb
import pytest

from src.api.queries import (
    expand_skill_ids,
    get_skill_detail,
    hard_soft_ratio,
    search_jobs,
    search_skills,
    top_skills,
)


@pytest.fixture
def con():
    con = duckdb.connect(":memory:")
    con.execute(
        "CREATE TABLE dim_skill (skill_id VARCHAR, canonical_name VARCHAR, skill_type VARCHAR, "
        "category VARCHAR, parent_skill_id VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO dim_skill VALUES
            ('lang', 'Ngôn ngữ lập trình', 'hard', NULL, NULL),
            ('python', 'Python', 'hard', 'Ngôn ngữ lập trình', 'lang'),
            ('java', 'Java', 'hard', 'Ngôn ngữ lập trình', 'lang'),
            ('teamwork', 'Làm việc nhóm', 'soft', NULL, NULL)
        """
    )
    con.execute("CREATE TABLE dim_skill_variant (variant_id INTEGER, skill_id VARCHAR, surface_form VARCHAR)")
    con.execute(
        "INSERT INTO dim_skill_variant VALUES (1, 'python', 'python3'), (2, 'python', 'py')"
    )
    con.execute("CREATE TABLE bridge_skill_closure (ancestor_id VARCHAR, descendant_id VARCHAR, depth INTEGER)")
    con.execute(
        """
        INSERT INTO bridge_skill_closure VALUES
            ('lang', 'lang', 0), ('python', 'python', 0), ('java', 'java', 0), ('teamwork', 'teamwork', 0),
            ('lang', 'python', 1), ('lang', 'java', 1)
        """
    )
    con.execute(
        "CREATE TABLE dim_job (job_id VARCHAR, title_raw VARCHAR, role_family VARCHAR, company_id INTEGER, "
        "location_id INTEGER, posted_date VARCHAR, source VARCHAR, url VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO dim_job VALUES
            ('j1', 'Backend Dev', 'Data Engineer', 1, 1, '2026-01-01', 'itviec', NULL),
            ('j2', 'Data Scientist', 'Data Engineer', 1, 1, '2026-02-01', 'data_jobs', NULL)
        """
    )
    con.execute("CREATE TABLE dim_company (company_id INTEGER, name VARCHAR, name_norm VARCHAR, industry VARCHAR)")
    con.execute("INSERT INTO dim_company VALUES (1, 'ACME', 'acme', NULL)")
    con.execute("CREATE TABLE dim_location (location_id INTEGER, location_raw VARCHAR, city_guess VARCHAR)")
    con.execute("INSERT INTO dim_location VALUES (1, 'Ha Noi', 'Ha Noi')")
    con.execute(
        "CREATE TABLE fact_job_skill (job_id VARCHAR, skill_id VARCHAR, skill_type VARCHAR, source VARCHAR, "
        "extraction_method VARCHAR, confidence DOUBLE, evidence_snippet VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO fact_job_skill VALUES
            ('j1', 'python', 'hard', 'itviec', 'source_provided', 100, 'Python'),
            ('j2', 'java', 'hard', 'data_jobs', 'source_provided', 100, 'Java'),
            ('j1', 'teamwork', 'soft', 'itviec', 'exact_match', 100, 'teamwork')
        """
    )
    return con


def test_search_skills_matches_canonical_and_variant(con):
    assert {r["skill_id"] for r in search_skills(con, "python")} == {"python"}
    assert {r["skill_id"] for r in search_skills(con, "py")} == {"python"}


def test_get_skill_detail_includes_parent_children_variants(con):
    detail = get_skill_detail(con, "python")
    assert detail["parent"]["skill_id"] == "lang"
    assert detail["job_count"] == 1
    assert set(detail["variants"]) == {"python3", "py"}

    parent_detail = get_skill_detail(con, "lang")
    assert {c["skill_id"] for c in parent_detail["children"]} == {"python", "java"}


def test_get_skill_detail_returns_none_for_unknown_id(con):
    assert get_skill_detail(con, "does-not-exist") is None


def test_expand_skill_ids_includes_self_and_descendants(con):
    assert set(expand_skill_ids(con, "lang")) == {"lang", "python", "java"}
    assert expand_skill_ids(con, "python") == ["python"]


def test_search_jobs_expands_general_skill_to_children(con):
    jobs = search_jobs(con, "lang", expand=True)
    assert {j["job_id"] for j in jobs} == {"j1", "j2"}


def test_search_jobs_without_expand_matches_only_exact_skill(con):
    jobs = search_jobs(con, "lang", expand=False)
    assert jobs == []
    jobs = search_jobs(con, "python", expand=False)
    assert {j["job_id"] for j in jobs} == {"j1"}


def test_top_skills_orders_by_job_count(con):
    ranked = top_skills(con, limit=10)
    assert ranked[0]["n"] >= ranked[-1]["n"]


def test_hard_soft_ratio_counts_by_type(con):
    ratio = hard_soft_ratio(con)
    assert ratio == {"hard": 2, "soft": 1}
