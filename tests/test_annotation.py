from src.eval.annotation import build_gold_rows, build_tasks, oov_skill_id, validate_annotations


def _record(source: str, source_id: int, length: int) -> dict:
    return {
        "source": source,
        "source_id": str(source_id),
        "title": f"Job {source_id}",
        "requirements_raw": "x" * length,
        "description": None,
        "is_canonical": True,
    }


def test_build_tasks_is_reproducible_and_stratified():
    records = [
        *[_record("itviec", index, index + 1) for index in range(12)],
        *[_record("vieclam24h", index, index + 1) for index in range(12)],
    ]

    first = build_tasks(records, per_source=6, seed=7, development_ratio=1 / 3)
    second = build_tasks(records, per_source=6, seed=7, development_ratio=1 / 3)

    assert first == second
    assert len(first) == 12
    assert {task["source"] for task in first} == {"itviec", "vieclam24h"}
    assert all(
        sum(task["source"] == source for task in first) == 6
        for source in ("itviec", "vieclam24h")
    )
    assert all(
        {task["length_band"] for task in first if task["source"] == source}
        == {"short", "medium", "long"}
        for source in ("itviec", "vieclam24h")
    )


def test_validation_rejects_unknown_dictionary_id():
    tasks = [{"task_id": "itviec:1"}]
    annotations = [
        {
            "task_id": "itviec:1",
            "annotator": "An",
            "status": "complete",
            "skill_ids": ["not-in-dictionary"],
            "unresolved_terms": [],
        }
    ]

    errors = validate_annotations(tasks, annotations, {"python"})

    assert errors == [
        "itviec:1: skill_id không có trong dictionary: ['not-in-dictionary']"
    ]


def test_gold_export_keeps_only_completed_tasks_when_allowed():
    tasks = [
        {
            "task_id": "itviec:1",
            "source": "itviec",
            "source_id": "1",
            "split": "test",
            "length_band": "short",
            "fields": {"title": "Python", "requirements_raw": None, "description": None},
            "input_sha256": "abc",
        },
        {
            "task_id": "vieclam24h:2",
            "source": "vieclam24h",
            "source_id": "2",
            "split": "development",
            "length_band": "long",
            "fields": {"title": "SQL", "requirements_raw": None, "description": None},
            "input_sha256": "def",
        },
    ]
    annotations = [
        {
            "task_id": "itviec:1",
            "annotator": "An",
            "status": "complete",
            "skill_ids": ["python", "python"],
            "unresolved_terms": ["Apache Airflow"],
            "updated_at": "2026-08-08T00:00:00+00:00",
        }
    ]

    rows = build_gold_rows(tasks, annotations, require_complete=False)

    assert len(rows) == 1
    assert rows[0]["gold_skill_ids"] == [oov_skill_id("Apache Airflow"), "python"]
    assert rows[0]["gold_oov_terms"] == ["Apache Airflow"]
