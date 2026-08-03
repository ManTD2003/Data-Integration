from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_search_skills_returns_python():
    resp = client.get("/skills", params={"q": "python"})
    assert resp.status_code == 200
    names = {row["canonical_name"] for row in resp.json()}
    assert "Python" in names


def test_skill_detail_for_unknown_id_is_404():
    resp = client.get("/skills/does-not-exist")
    assert resp.status_code == 404


def test_skill_detail_returns_expected_shape():
    skill_id = client.get("/skills", params={"q": "python"}).json()[0]["skill_id"]
    resp = client.get(f"/skills/{skill_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) >= {"skill_id", "canonical_name", "skill_type", "variants", "job_count", "evidence_samples"}


def test_search_jobs_expands_hierarchy():
    lang_id = next(
        row["skill_id"]
        for row in client.get("/skills", params={"q": "Ngôn ngữ lập trình"}).json()
        if row["canonical_name"] == "Ngôn ngữ lập trình"
    )
    resp = client.get("/jobs/search", params={"skill_id": lang_id, "expand": True, "limit": 5})
    assert resp.status_code == 200
    assert len(resp.json()) > 0


def test_top_skills_returns_ranked_list():
    resp = client.get("/stats/top-skills", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5
    assert body[0]["n"] >= body[-1]["n"]


def test_hard_soft_ratio_has_both_types():
    resp = client.get("/stats/hard-soft-ratio")
    assert resp.status_code == 200
    assert set(resp.json()) <= {"hard", "soft"}
