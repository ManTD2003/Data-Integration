"""Các hàm tính chỉ số dùng chung cho mọi phép đo trong `src/eval`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SetScore:
    """Đếm tp/fp/fn khi so hai tập nhãn (mỗi bản ghi một tập kỹ năng)."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def update(self, gold: set[str], pred: set[str]) -> None:
        self.tp += len(gold & pred)
        self.fp += len(pred - gold)
        self.fn += len(gold - pred)

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


def reciprocal_rank(ranked: list[str], expected: str) -> float:
    for position, item in enumerate(ranked, start=1):
        if item == expected:
            return 1.0 / position
    return 0.0


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
