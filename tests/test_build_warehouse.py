import pandas as pd
import pytest

from src.warehouse.build_warehouse import (
    build_dim_skill,
    build_dim_skill_term,
    check_integrity,
    search_terms,
)


def test_build_dim_skill_fills_category_from_parent():
    skills = [
        {"skill_id": "cat", "canonical_name": "Ngôn ngữ lập trình", "skill_type": "hard", "parent_skill_id": None},
        {"skill_id": "py", "canonical_name": "Python", "skill_type": "hard", "parent_skill_id": "cat"},
    ]
    df = build_dim_skill(skills)
    row = df[df["skill_id"] == "py"].iloc[0]
    assert row["category"] == "Ngôn ngữ lập trình"
    assert not row["is_category"]


def test_search_terms_cover_accentless_and_compact_forms():
    terms = search_terms({"canonical_name": "Tiếng Anh", "aliases": ["tiếng anh", "english"]})
    assert {"tiếng anh", "tieng anh", "tienganh", "english"} <= terms


def test_search_terms_keep_symbols():
    terms = search_terms({"canonical_name": "C++", "aliases": ["c++"]})
    assert "c++" in terms


def test_build_dim_skill_term_lists_one_row_per_term():
    skills = [{"skill_id": "next", "canonical_name": "NextJS", "aliases": ["nextjs", "next js"]}]
    df = build_dim_skill_term(skills)
    assert set(df["skill_id"]) == {"next"}
    assert {"nextjs", "next js"} <= set(df["term"])


def _tables(**overrides) -> dict[str, pd.DataFrame]:
    tables = {
        "dim_skill": pd.DataFrame(
            [
                {
                    "skill_id": "cat",
                    "canonical_name": "Ngôn ngữ lập trình",
                    "category": None,
                    "parent_skill_id": None,
                    "is_category": True,
                },
                {
                    "skill_id": "py",
                    "canonical_name": "Python",
                    "category": "Ngôn ngữ lập trình",
                    "parent_skill_id": "cat",
                    "is_category": False,
                },
            ]
        ),
        "dim_job": pd.DataFrame([{"job_id": "j1"}]),
        "fact_job_skill": pd.DataFrame([{"job_id": "j1", "skill_id": "py"}]),
        "dim_skill_term": pd.DataFrame(
            [{"skill_id": "cat", "term": "ngon ngu lap trinh"}, {"skill_id": "py", "term": "python"}]
        ),
        "bridge_skill_closure": pd.DataFrame(
            [
                {"ancestor_id": "cat", "descendant_id": "cat", "depth": 0},
                {"ancestor_id": "py", "descendant_id": "py", "depth": 0},
                {"ancestor_id": "cat", "descendant_id": "py", "depth": 1},
            ]
        ),
    }
    tables.update(overrides)
    return tables


def test_check_integrity_accepts_consistent_tables():
    check_integrity(_tables())


def test_check_integrity_rejects_closure_pointing_outside_dim_skill():
    closure = pd.DataFrame([{"ancestor_id": "cat", "descendant_id": "ghost", "depth": 1}])
    with pytest.raises(ValueError, match="bridge_skill_closure"):
        check_integrity(_tables(bridge_skill_closure=closure))


def test_check_integrity_rejects_fact_pointing_at_unknown_job():
    fact = pd.DataFrame([{"job_id": "j404", "skill_id": "py"}])
    with pytest.raises(ValueError, match="fact_job_skill.job_id"):
        check_integrity(_tables(fact_job_skill=fact))


def test_check_integrity_rejects_missing_hierarchy():
    skills = pd.DataFrame(
        [
            {
                "skill_id": "py",
                "canonical_name": "Python",
                "category": None,
                "parent_skill_id": None,
                "is_category": False,
            }
        ]
    )
    closure = pd.DataFrame([{"ancestor_id": "py", "descendant_id": "py", "depth": 0}])
    with pytest.raises(ValueError, match="build_hierarchy"):
        check_integrity(_tables(dim_skill=skills, bridge_skill_closure=closure))


def test_check_integrity_rejects_fact_on_category_node():
    """Nút nhóm có dòng fact nghĩa là bước trích chọn đã chạy trên từ điển đã gắn
    phân cấp, tức kết quả phụ thuộc thứ tự chạy pipeline."""
    fact = pd.DataFrame([{"job_id": "j1", "skill_id": "cat"}])
    with pytest.raises(ValueError, match="nút nhóm"):
        check_integrity(_tables(fact_job_skill=fact))


def test_check_integrity_rejects_term_pointing_outside_dim_skill():
    terms = pd.DataFrame([{"skill_id": "ghost", "term": "ma"}])
    with pytest.raises(ValueError, match="dim_skill_term"):
        check_integrity(_tables(dim_skill_term=terms))
