import json

import pytest

from src.integration import build_staging


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(build_staging, "RAW", tmp_path)
    return tmp_path


def _write(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_raw_key_uses_the_id_field_of_each_source():
    assert build_staging.raw_key({"_source": "vieclam24h", "id": 7}) == "vieclam24h:7"
    assert build_staging.raw_key({"_source": "itviec", "job_key": "abc"}) == "itviec:abc"
    assert build_staging.raw_key({"_source": "data_jobs", "_row_id": 3}) == "data_jobs:3"


def test_second_crawl_of_the_same_job_is_loaded_once(raw_dir):
    """Mỗi lượt cào ghi ra một file mới và các lượt chồng lấn nhau; nạp tất cả thì mọi
    số đếm theo nguồn đều bị thổi lên."""
    _write(raw_dir / "vieclam24h_20260101_000000.jsonl", [{"_source": "vieclam24h", "id": 1, "title": "cũ"}])
    _write(raw_dir / "vieclam24h_20260102_000000.jsonl", [{"_source": "vieclam24h", "id": 1, "title": "mới"}])

    records = list(build_staging.iter_raw())

    assert len(records) == 1
    assert records[0]["title"] == "mới"


def test_records_from_different_sources_are_kept_apart(raw_dir):
    _write(raw_dir / "a_20260101_000000.jsonl", [{"_source": "vieclam24h", "id": 1}])
    _write(raw_dir / "b_20260101_000000.jsonl", [{"_source": "itviec", "job_key": 1}])

    assert len(list(build_staging.iter_raw())) == 2
