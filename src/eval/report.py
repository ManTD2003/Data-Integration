"""In bảng chỉ số tổng hợp. Chạy: `python -m src.eval.report`."""

from __future__ import annotations

import argparse
import json

from src.api import queries as query_layer
from src.eval import extraction, integrity, retrieval


def _pct(value: float) -> str:
    return f"{value:.3f}"


def _print_extraction(result: dict) -> None:
    print(f"Trích xuất kỹ năng — silver standard, n={result['n_records']} tin")
    overall = result["overall"]
    print(
        f"  chung                P={_pct(overall['precision'])}  R={_pct(overall['recall'])}  F1={_pct(overall['f1'])}"
    )
    for source, score in sorted(result["per_source"].items()):
        print(
            f"  {source:<20} P={_pct(score['precision'])}  R={_pct(score['recall'])}  "
            f"F1={_pct(score['f1'])}  (tp={score['tp']}, fp={score['fp']}, fn={score['fn']})"
        )
    for method, score in sorted(result["per_method"].items()):
        print(f"  method {method:<13} P={_pct(score['precision'])}  n={score['n']}")
    print("  Lưu ý: nhãn của site không đầy đủ nên P là chặn dưới; data_jobs chỉ đo trên title.")


def _print_retrieval(result: dict) -> None:
    search = result["skill_search"]
    print(f"Tìm kiếm kỹ năng — n={search['n']} truy vấn gán tay")
    print(f"  P@1={_pct(search['p_at_1'])}  MRR={_pct(search['mrr'])}  không tìm thấy={search['not_found']}")
    for kind, score in search["per_kind"].items():
        print(f"  {kind:<20} MRR={_pct(score['mrr'])}  n={score['n']}")
    if search["misses"]:
        print("  Truy vấn trượt:")
        for miss in search["misses"]:
            print(f"    \"{miss['q']}\" cần {miss['expect']}, nhận {miss['got']}")

    expansion = result["expansion"]
    print(
        f"Mở rộng phân cấp — {expansion['n_ancestors']}/{expansion['n_skills']} skill có hậu duệ, "
        f"lệch so với parent_skill_id: {len(expansion['mismatch'])}"
    )
    for item in expansion["mismatch"][:5]:
        print(f"    {item['skill_id']} thiếu {item['missing']}")


def _print_integrity(checks: list[tuple[str, bool, str]]) -> None:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"Toàn vẹn kho — {passed}/{len(checks)} ràng buộc")
    for label, ok, detail in checks:
        if not ok:
            print(f"  LỖI {label}: {detail}")


def run(as_json: bool = False) -> dict:
    con = query_layer.get_connection()
    try:
        result = {
            "extraction": extraction.run(),
            "retrieval": retrieval.run(con),
            "integrity": [
                {"check": label, "ok": ok, "detail": detail} for label, ok, detail in integrity.run_checks(con)
            ],
        }
    finally:
        con.close()

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result

    _print_extraction(result["extraction"])
    print()
    _print_retrieval(result["retrieval"])
    print()
    _print_integrity([(c["check"], c["ok"], c["detail"]) for c in result["integrity"]])
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="in kết quả thô để lưu lại giữa các lần chạy")
    args = ap.parse_args()
    run(as_json=args.json)


if __name__ == "__main__":
    main()
