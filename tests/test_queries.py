import duckdb
import pytest

from src.api.queries import (
    corpus_stats,
    expand_skill_ids,
    get_skill_detail,
    hard_soft_ratio,
    jobs_by_month,
    jobs_by_skill_category,
    list_cities,
    list_countries,
    salary_band_by_role_family,
    search_jobs,
    search_skills,
    skill_cooccurrence,
    skill_type_by_role_family,
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
    con.execute("CREATE TABLE dim_skill_term (skill_id VARCHAR, term VARCHAR)")
    con.execute(
        """
        INSERT INTO dim_skill_term VALUES
            ('lang', 'ngôn ngữ lập trình'), ('lang', 'ngon ngu lap trinh'), ('lang', 'ngonngulaptrinh'),
            ('python', 'python'), ('python', 'python3'), ('python', 'py'),
            ('java', 'java'),
            ('teamwork', 'làm việc nhóm'), ('teamwork', 'lam viec nhom'), ('teamwork', 'lamviecnhom')
        """
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
        "location_id INTEGER, posted_date VARCHAR, source VARCHAR, url VARCHAR, seniority VARCHAR, "
        "salary_min DOUBLE, salary_max DOUBLE, salary_currency VARCHAR, salary_period VARCHAR)"
    )
    con.execute(
        """
        INSERT INTO dim_job VALUES
            ('j1', 'Backend Dev', 'Kỹ sư phần mềm', 1, 1, '2026-01-01', 'itviec', NULL, NULL,
             15000000, 20000000, 'VND', 'month'),
            ('j2', 'Data Scientist', 'Khoa học dữ liệu', 1, 1, '2026-02-01', 'data_jobs', NULL, 'Cao cấp',
             95000, 95000, 'USD', 'year')
        """
    )
    con.execute("CREATE TABLE dim_company (company_id INTEGER, name VARCHAR, name_norm VARCHAR, industry VARCHAR)")
    con.execute("INSERT INTO dim_company VALUES (1, 'ACME', 'acme', NULL)")
    con.execute("CREATE TABLE dim_location (location_id INTEGER, location_raw VARCHAR, city VARCHAR, country VARCHAR)")
    con.execute("INSERT INTO dim_location VALUES (1, 'Ha Noi', 'Hà Nội', 'Việt Nam')")
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


def test_search_skills_ignores_diacritics(con):
    assert [r["skill_id"] for r in search_skills(con, "lam viec nhom")] == ["teamwork"]
    assert [r["skill_id"] for r in search_skills(con, "Làm việc nhóm")] == ["teamwork"]


def test_search_skills_ignores_spacing(con):
    assert [r["skill_id"] for r in search_skills(con, "ngonngu lap trinh")] == ["lang"]


def test_search_skills_ranks_exact_match_first(con):
    """Xếp theo tên thì 'java' trả về Java sau các tên đứng trước theo alphabet."""
    con.execute("INSERT INTO dim_skill VALUES ('javascript', 'JavaScript', 'hard', NULL, NULL)")
    con.execute("INSERT INTO dim_skill_term VALUES ('javascript', 'javascript')")
    assert [r["skill_id"] for r in search_skills(con, "java")] == ["java", "javascript"]


def test_search_skills_escapes_like_wildcards(con):
    assert search_skills(con, "%") == []
    assert search_skills(con, "_") == []


def test_search_skills_empty_query_returns_nothing(con):
    assert search_skills(con, "   ") == []


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


def test_hard_soft_ratio_counts_jobs_not_fact_rows(con):
    """Cùng đơn vị với top_skills: một tin đòi hai kỹ năng cứng vẫn chỉ tính một lần."""
    con.execute(
        "INSERT INTO fact_job_skill VALUES ('j1', 'java', 'hard', 'itviec', 'exact_match', 100, 'Java')"
    )
    assert hard_soft_ratio(con) == {"hard": 2, "soft": 1}


def test_search_jobs_offers_link_back_to_source(con):
    jobs = search_jobs(con, "python", expand=False)
    assert jobs[0]["source_search_url"].startswith("https://itviec.com/it-jobs?query=")


def test_list_cities_hides_values_below_threshold(con):
    assert list_cities(con, min_jobs=5) == []
    assert list_cities(con, min_jobs=1) == ["Hà Nội"]


def test_list_cities_scopes_to_country(con):
    con.execute("INSERT INTO dim_location VALUES (2, 'Austin, TX', 'Austin', 'United States')")
    con.execute(
        "INSERT INTO dim_job VALUES ('j3', 'ML Engineer', 'Khoa học dữ liệu', 1, 2, "
        "'2026-03-01', 'data_jobs', NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    assert list_cities(con, min_jobs=1) == ["Hà Nội", "Austin"]
    assert list_cities(con, country="Việt Nam", min_jobs=1) == ["Hà Nội"]
    assert list_countries(con, min_jobs=1) == ["Việt Nam", "United States"]


def test_corpus_stats_counts_jobs_and_pairs(con):
    stats = corpus_stats(con)
    assert (stats["n_jobs"], stats["n_sources"], stats["n_pairs"], stats["n_skills"]) == (2, 2, 3, 3)
    assert stats["skills_per_job"] == pytest.approx(1.5)


def test_corpus_stats_follows_the_filter(con):
    assert corpus_stats(con, role_family="Kỹ sư phần mềm")["n_jobs"] == 1
    assert corpus_stats(con, city="Đà Nẵng")["n_jobs"] == 0


def test_skill_type_by_role_family_counts_a_job_in_both_types(con):
    rows = {(r["role_family"], r["skill_type"]): r["n"] for r in skill_type_by_role_family(con)}
    assert rows[("Kỹ sư phần mềm", "hard")] == 1
    assert rows[("Kỹ sư phần mềm", "soft")] == 1


def test_jobs_by_skill_category_skips_skills_without_category(con):
    rows = jobs_by_skill_category(con)
    assert [(r["category"], r["n"]) for r in rows] == [("Ngôn ngữ lập trình", 2)]


def test_skill_cooccurrence_is_symmetric_and_keeps_the_diagonal(con):
    rows = {(r["skill_a"], r["skill_b"]): r["n"] for r in skill_cooccurrence(con)}
    assert rows[("Python", "Làm việc nhóm")] == rows[("Làm việc nhóm", "Python")] == 1
    assert rows[("Python", "Python")] == 1
    assert ("Python", "Java") not in rows


def test_salary_band_keeps_one_currency_and_period(con):
    """Kho không quy đổi tỷ giá nên tin USD/năm không được lẫn vào cùng trục với VNĐ."""
    rows = salary_band_by_role_family(con, min_jobs=1)
    assert [(r["role_family"], r["low"], r["high"]) for r in rows] == [
        ("Kỹ sư phần mềm", 15000000, 20000000)
    ]
    assert salary_band_by_role_family(con, currency="USD", period="year", min_jobs=1)[0][
        "role_family"
    ] == "Khoa học dữ liệu"


def test_jobs_by_month_groups_by_month_and_source(con):
    rows = jobs_by_month(con)
    assert [(r["month"], r["source"], r["n"]) for r in rows] == [
        ("2026-01", "itviec", 1),
        ("2026-02", "data_jobs", 1),
    ]


def test_search_jobs_filters_by_country(con):
    con.execute("INSERT INTO dim_location VALUES (2, 'Austin, TX', 'Austin', 'United States')")
    con.execute("UPDATE dim_job SET location_id = 2 WHERE job_id = 'j2'")
    assert {j["job_id"] for j in search_jobs(con, "lang", country="Việt Nam")} == {"j1"}
    assert {j["job_id"] for j in search_jobs(con, "lang", country="United States")} == {"j2"}
