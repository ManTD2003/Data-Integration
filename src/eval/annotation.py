"""Tạo và quản lý gold standard cho bài toán skill extraction."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.common.paths import EVAL, STAGING
from src.eval.metrics import SetScore
from src.process.extract_skills import (
    MIN_FUZZY_TOKEN_LEN,
    common_tokens,
    extract_from_text,
)
from src.process.skill_dictionary import DICTIONARY_PATH, SkillDictionary

TASKS_PATH = EVAL / "skill_extraction_tasks.jsonl"
ANNOTATIONS_PATH = EVAL / "skill_extraction_annotations.jsonl"
GOLD_PATH = EVAL / "skill_extraction_gold.jsonl"
MANIFEST_PATH = EVAL / "skill_extraction_manifest.json"
RECORDS_PATH = STAGING / "records_deduped.jsonl"
EXTRACTOR_PATH = Path(__file__).resolve().parents[1] / "process" / "extract_skills.py"
SIMILARITY_PATH = Path(__file__).resolve().parents[1] / "common" / "similarity.py"

ANNOTATION_FIELDS = ("title", "requirements_raw", "description")
DEFAULT_SOURCES = ("itviec", "vieclam24h")
LENGTH_BANDS = ("short", "medium", "long")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_sha256(fields: dict[str, str | None]) -> str:
    payload = json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def oov_skill_id(term: str) -> str:
    normalized = " ".join(term.casefold().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"oov:{digest}"


def _text_length(record: dict) -> int:
    return sum(len(str(record.get(field) or "")) for field in ANNOTATION_FIELDS)


def _with_length_bands(records: list[dict]) -> list[tuple[dict, str]]:
    ordered = sorted(records, key=lambda record: (_text_length(record), record["source_id"]))
    total = len(ordered)
    return [
        (record, LENGTH_BANDS[min(len(LENGTH_BANDS) - 1, rank * len(LENGTH_BANDS) // total)])
        for rank, record in enumerate(ordered)
    ]


def _sample_source(records: list[dict], size: int, rng: random.Random) -> list[tuple[dict, str]]:
    banded = _with_length_bands(records)
    buckets = {
        band: [record for record, assigned_band in banded if assigned_band == band]
        for band in LENGTH_BANDS
    }
    quotas = {
        band: size // len(LENGTH_BANDS) + (index < size % len(LENGTH_BANDS))
        for index, band in enumerate(LENGTH_BANDS)
    }
    selected: list[tuple[dict, str]] = []
    for band in LENGTH_BANDS:
        selected.extend((record, band) for record in rng.sample(buckets[band], quotas[band]))
    return selected


def build_tasks(
    records: list[dict],
    per_source: int = 100,
    seed: int = 5420,
    development_ratio: float = 0.3,
    sources: tuple[str, ...] = DEFAULT_SOURCES,
) -> list[dict]:
    if per_source < 1:
        raise ValueError("per_source phải lớn hơn 0")
    if not 0 < development_ratio < 1:
        raise ValueError("development_ratio phải nằm trong khoảng (0, 1)")

    rng = random.Random(seed)
    tasks: list[dict] = []
    for source in sources:
        candidates = [
            record
            for record in records
            if record.get("source") == source
            and record.get("is_canonical", True)
            and _text_length(record) > 0
        ]
        if len(candidates) < per_source:
            raise ValueError(f"{source} chỉ có {len(candidates)} tin phù hợp, cần {per_source}")

        sampled = _sample_source(candidates, per_source, rng)
        by_band: dict[str, list[dict]] = {band: [] for band in LENGTH_BANDS}
        for record, band in sampled:
            by_band[band].append(record)

        for band in LENGTH_BANDS:
            rng.shuffle(by_band[band])
            development_count = round(len(by_band[band]) * development_ratio)
            for index, record in enumerate(by_band[band]):
                fields = {field: record.get(field) for field in ANNOTATION_FIELDS}
                tasks.append(
                    {
                        "task_id": f"{source}:{record['source_id']}",
                        "source": source,
                        "source_id": str(record["source_id"]),
                        "url": record.get("url"),
                        "company": record.get("company"),
                        "length_band": band,
                        "split": "development" if index < development_count else "test",
                        "fields": fields,
                        "input_sha256": input_sha256(fields),
                    }
                )

    rng.shuffle(tasks)
    for order, task in enumerate(tasks, start=1):
        task["order"] = order
    return tasks


def load_skill_dictionary(path: Path = DICTIONARY_PATH) -> SkillDictionary:
    skill_dict = SkillDictionary()
    for entry in json.loads(path.read_text(encoding="utf-8")):
        entry.setdefault("is_category", False)
        skill_dict.skills[entry["skill_id"]] = entry
        for alias in entry["aliases"]:
            skill_dict.alias_index[alias] = entry["skill_id"]
    return skill_dict.for_extraction()


def save_annotation(annotation: dict, path: Path = ANNOTATIONS_PATH) -> None:
    rows = read_jsonl(path)
    by_task = {row["task_id"]: row for row in rows}
    by_task[annotation["task_id"]] = annotation
    write_jsonl(path, sorted(by_task.values(), key=lambda row: row["task_id"]))


def validate_annotations(
    tasks: list[dict], annotations: list[dict], valid_skill_ids: set[str]
) -> list[str]:
    errors: list[str] = []
    task_ids = {task["task_id"] for task in tasks}
    seen: set[str] = set()
    for annotation in annotations:
        task_id = annotation.get("task_id")
        if task_id in seen:
            errors.append(f"Nhãn trùng task_id: {task_id}")
        seen.add(task_id)
        if task_id not in task_ids:
            errors.append(f"Nhãn không có task tương ứng: {task_id}")
        if annotation.get("status") not in {"draft", "complete"}:
            errors.append(f"{task_id}: status không hợp lệ")
        unknown = set(annotation.get("skill_ids", [])) - valid_skill_ids
        if unknown:
            errors.append(f"{task_id}: skill_id không có trong dictionary: {sorted(unknown)}")
        if not str(annotation.get("annotator") or "").strip():
            errors.append(f"{task_id}: thiếu tên người gán nhãn")
    return errors


def build_gold_rows(
    tasks: list[dict], annotations: list[dict], require_complete: bool = True
) -> list[dict]:
    by_task = {annotation["task_id"]: annotation for annotation in annotations}
    incomplete = [
        task["task_id"]
        for task in tasks
        if by_task.get(task["task_id"], {}).get("status") != "complete"
    ]
    if require_complete and incomplete:
        raise ValueError(f"Còn {len(incomplete)} task chưa hoàn thành")

    rows = []
    for task in tasks:
        annotation = by_task.get(task["task_id"])
        if not annotation or annotation.get("status") != "complete":
            continue
        oov_terms = sorted(
            {term.strip() for term in annotation.get("unresolved_terms", []) if term.strip()},
            key=str.casefold,
        )
        gold_skill_ids = set(annotation.get("skill_ids", []))
        gold_skill_ids.update(oov_skill_id(term) for term in oov_terms)
        rows.append(
            {
                "task_id": task["task_id"],
                "source": task["source"],
                "source_id": task["source_id"],
                "split": task["split"],
                "length_band": task["length_band"],
                "fields": task["fields"],
                "input_sha256": task["input_sha256"],
                "gold_skill_ids": sorted(gold_skill_ids),
                "gold_oov_terms": oov_terms,
                "annotator": annotation["annotator"],
                "annotated_at": annotation["updated_at"],
            }
        )
    return rows


def evaluate_gold(
    gold_rows: list[dict],
    skill_dict: SkillDictionary,
    corpus_records: list[dict],
    split: str = "test",
) -> dict:
    aliases = [
        alias
        for alias in skill_dict.alias_index
        if " " not in alias and len(alias) >= MIN_FUZZY_TOKEN_LEN
    ]
    common = common_tokens(corpus_records)
    overall = SetScore()
    in_vocabulary = SetScore()
    per_source: dict[str, SetScore] = {}
    per_source_in_vocabulary: dict[str, SetScore] = {}
    per_job_f1: list[float] = []
    per_job_in_vocabulary_f1: list[float] = []
    method_hits: dict[str, list[int]] = {}
    gold_pair_count = 0
    oov_pair_count = 0
    count = 0

    for row in gold_rows:
        if split != "all" and row["split"] != split:
            continue
        gold = set(row["gold_skill_ids"])
        gold_in_vocabulary = {skill_id for skill_id in gold if not skill_id.startswith("oov:")}
        matches = extract_from_text(row["fields"], skill_dict, aliases, common)
        predicted = {match["skill_id"] for match in matches}
        overall.update(gold, predicted)
        in_vocabulary.update(gold_in_vocabulary, predicted)
        per_source.setdefault(row["source"], SetScore()).update(gold, predicted)
        per_source_in_vocabulary.setdefault(row["source"], SetScore()).update(
            gold_in_vocabulary, predicted
        )
        pair_score = SetScore()
        pair_score.update(gold, predicted)
        per_job_f1.append(pair_score.f1)
        in_vocabulary_pair_score = SetScore()
        in_vocabulary_pair_score.update(gold_in_vocabulary, predicted)
        per_job_in_vocabulary_f1.append(in_vocabulary_pair_score.f1)
        gold_pair_count += len(gold)
        oov_pair_count += len(gold - gold_in_vocabulary)
        for match in matches:
            hit, total = method_hits.setdefault(match["method"], [0, 0])
            method_hits[match["method"]] = [hit + (match["skill_id"] in gold), total + 1]
        count += 1

    standard = (
        "llm_assisted_gold"
        if gold_rows and all(row.get("annotator") == "codex" for row in gold_rows)
        else "manual_gold"
    )
    return {
        "standard": standard,
        "split": split,
        "n_records": count,
        "overall": {**overall.as_dict(), "macro_f1": sum(per_job_f1) / count if count else 0.0},
        "in_vocabulary": {
            **in_vocabulary.as_dict(),
            "macro_f1": sum(per_job_in_vocabulary_f1) / count if count else 0.0,
        },
        "dictionary_coverage": {
            "gold_pairs": gold_pair_count,
            "oov_pairs": oov_pair_count,
            "coverage": (gold_pair_count - oov_pair_count) / gold_pair_count
            if gold_pair_count
            else 0.0,
        },
        "per_source": {source: score.as_dict() for source, score in per_source.items()},
        "per_source_in_vocabulary": {
            source: score.as_dict() for source, score in per_source_in_vocabulary.items()
        },
        "per_method": {
            method: {"n": total, "precision": hits / total if total else 0.0}
            for method, (hits, total) in method_hits.items()
        },
    }


def _manifest(tasks: list[dict], seed: int, per_source: int, development_ratio: float) -> dict:
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "per_source": per_source,
        "development_ratio": development_ratio,
        "sources": list(DEFAULT_SOURCES),
        "input_fields": list(ANNOTATION_FIELDS),
        "task_count": len(tasks),
        "test_frozen": False,
        "dictionary_sha256": file_sha256(DICTIONARY_PATH),
        "extractor_sha256": file_sha256(EXTRACTOR_PATH),
        "similarity_sha256": file_sha256(SIMILARITY_PATH),
        "records_sha256": file_sha256(RECORDS_PATH),
    }


def command_init(args: argparse.Namespace) -> None:
    existing = [path for path in (TASKS_PATH, ANNOTATIONS_PATH, GOLD_PATH) if path.exists()]
    if existing and not args.force:
        names = ", ".join(path.name for path in existing)
        raise SystemExit(f"Đã có {names}; dùng --force nếu muốn tạo lại toàn bộ batch")
    records = read_jsonl(RECORDS_PATH)
    tasks = build_tasks(records, args.per_source, args.seed, args.development_ratio)
    write_jsonl(TASKS_PATH, tasks)
    if args.force:
        write_jsonl(ANNOTATIONS_PATH, [])
        if GOLD_PATH.exists():
            GOLD_PATH.unlink()
    MANIFEST_PATH.write_text(
        json.dumps(
            _manifest(tasks, args.seed, args.per_source, args.development_ratio),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    counts = Counter((task["source"], task["split"]) for task in tasks)
    print(f"Đã tạo {len(tasks)} task tại {TASKS_PATH}")
    for (source, split), count in sorted(counts.items()):
        print(f"  {source:12} {split:11} {count}")


def _load_and_validate() -> tuple[list[dict], list[dict], list[str]]:
    tasks = read_jsonl(TASKS_PATH)
    annotations = read_jsonl(ANNOTATIONS_PATH)
    if not tasks:
        raise SystemExit("Chưa có batch; chạy ./run.sh annotate init")
    skill_dict = load_skill_dictionary()
    errors = validate_annotations(tasks, annotations, set(skill_dict.skills))
    for task in tasks:
        if task.get("input_sha256") != input_sha256(task.get("fields", {})):
            errors.append(f"{task.get('task_id')}: nội dung task không khớp checksum")
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if manifest.get("records_sha256") != file_sha256(RECORDS_PATH):
            errors.append("records_deduped.jsonl đã thay đổi sau khi tạo batch")
        if manifest.get("test_frozen"):
            if manifest.get("dictionary_sha256") != file_sha256(DICTIONARY_PATH):
                errors.append("skill_dictionary.json đã thay đổi sau khi khóa test split")
            if manifest.get("extractor_sha256") != file_sha256(EXTRACTOR_PATH):
                errors.append("extract_skills.py đã thay đổi sau khi khóa test split")
            if manifest.get("similarity_sha256") != file_sha256(SIMILARITY_PATH):
                errors.append("similarity.py đã thay đổi sau khi khóa test split")
    return tasks, annotations, errors


def command_status(_args: argparse.Namespace) -> None:
    tasks, annotations, errors = _load_and_validate()
    by_task = {annotation["task_id"]: annotation for annotation in annotations}
    counts = Counter(by_task.get(task["task_id"], {}).get("status", "unlabeled") for task in tasks)
    print(f"Tổng task: {len(tasks)}")
    for status in ("complete", "draft", "unlabeled"):
        print(f"  {status:9} {counts[status]}")
    tasks_with_oov = sum(bool(annotation.get("unresolved_terms")) for annotation in annotations)
    print(f"  tasks_with_oov {tasks_with_oov}")
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        print(f"  test_frozen {bool(manifest.get('test_frozen'))}")
    if errors:
        print("Lỗi kiểm tra:")
        for error in errors:
            print(f"  - {error}")


def command_freeze(_args: argparse.Namespace) -> None:
    tasks = read_jsonl(TASKS_PATH)
    annotations = read_jsonl(ANNOTATIONS_PATH)
    if not tasks or not MANIFEST_PATH.exists():
        raise SystemExit("Chưa có batch; chạy ./run.sh annotate init")
    errors = validate_annotations(tasks, annotations, set(load_skill_dictionary().skills))
    for task in tasks:
        if task.get("input_sha256") != input_sha256(task.get("fields", {})):
            errors.append(f"{task.get('task_id')}: nội dung task không khớp checksum")
    by_task = {annotation["task_id"]: annotation for annotation in annotations}
    unfinished = [
        task["task_id"]
        for task in tasks
        if task["split"] == "development"
        and by_task.get(task["task_id"], {}).get("status") != "complete"
    ]
    test_started = [
        task["task_id"]
        for task in tasks
        if task["split"] == "test" and task["task_id"] in by_task
    ]
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("records_sha256") != file_sha256(RECORDS_PATH):
        errors.append("records_deduped.jsonl đã thay đổi sau khi tạo batch")
    if unfinished:
        errors.append(f"còn {len(unfinished)} development task chưa hoàn thành")
    if test_started:
        errors.append(f"đã có {len(test_started)} test task được mở trước khi khóa")
    if errors:
        raise SystemExit("Không thể khóa test split:\n  - " + "\n  - ".join(errors))

    manifest["test_frozen"] = True
    manifest["frozen_at"] = datetime.now(timezone.utc).isoformat()
    manifest["dictionary_sha256"] = file_sha256(DICTIONARY_PATH)
    manifest["extractor_sha256"] = file_sha256(EXTRACTOR_PATH)
    manifest["similarity_sha256"] = file_sha256(SIMILARITY_PATH)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("Đã khóa dictionary, extractor và test split")


def command_export(args: argparse.Namespace) -> None:
    tasks, annotations, errors = _load_and_validate()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not manifest.get("test_frozen"):
        errors.append("test split chưa được khóa; chạy ./run.sh annotate freeze")
    if errors:
        raise SystemExit("Không thể export:\n  - " + "\n  - ".join(errors))
    try:
        rows = build_gold_rows(tasks, annotations, require_complete=not args.allow_incomplete)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    write_jsonl(GOLD_PATH, rows)
    counts = Counter((row["source"], row["split"]) for row in rows)
    print(f"Đã export {len(rows)} tin vào {GOLD_PATH}")
    for (source, split), count in sorted(counts.items()):
        print(f"  {source:12} {split:11} {count}")


def command_score(args: argparse.Namespace) -> None:
    _tasks, _annotations, errors = _load_and_validate()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not manifest.get("test_frozen"):
        errors.append("test split chưa được khóa; chạy ./run.sh annotate freeze")
    if errors:
        raise SystemExit("Không thể score:\n  - " + "\n  - ".join(errors))
    rows = read_jsonl(GOLD_PATH)
    if not rows:
        raise SystemExit("Chưa có gold standard; chạy ./run.sh annotate export")
    records = read_jsonl(RECORDS_PATH)
    result = evaluate_gold(rows, load_skill_dictionary(), records, args.split)
    if args.json:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return
    overall = result["overall"]
    standard_name = (
        "LLM-assisted gold" if result["standard"] == "llm_assisted_gold" else "Manual gold"
    )
    print(f"{standard_name}, split={args.split}, n={result['n_records']}")
    print(
        f"  end-to-end P={overall['precision']:.3f} R={overall['recall']:.3f} "
        f"F1={overall['f1']:.3f} | macro F1={overall['macro_f1']:.3f}"
    )
    in_vocabulary = result["in_vocabulary"]
    coverage = result["dictionary_coverage"]
    print(
        f"  in-vocabulary P={in_vocabulary['precision']:.3f} "
        f"R={in_vocabulary['recall']:.3f} F1={in_vocabulary['f1']:.3f} | "
        f"dictionary coverage={coverage['coverage']:.3f}"
    )
    for source, score in sorted(result["per_source"].items()):
        print(
            f"  {source:12} P={score['precision']:.3f} R={score['recall']:.3f} "
            f"F1={score['f1']:.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Workflow gán nhãn skill extraction")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Tạo batch gán nhãn cố định")
    init_parser.add_argument("--per-source", type=int, default=100)
    init_parser.add_argument("--seed", type=int, default=5420)
    init_parser.add_argument("--development-ratio", type=float, default=0.3)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(func=command_init)

    status_parser = subparsers.add_parser("status", help="Xem tiến độ và lỗi dữ liệu")
    status_parser.set_defaults(func=command_status)

    freeze_parser = subparsers.add_parser("freeze", help="Khóa hệ thống trước khi gán test")
    freeze_parser.set_defaults(func=command_freeze)

    export_parser = subparsers.add_parser("export", help="Xuất gold standard")
    export_parser.add_argument("--allow-incomplete", action="store_true")
    export_parser.set_defaults(func=command_export)

    score_parser = subparsers.add_parser("score", help="Đánh giá extractor trên manual gold")
    score_parser.add_argument("--split", choices=("development", "test", "all"), default="test")
    score_parser.add_argument("--json", action="store_true")
    score_parser.set_defaults(func=command_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
