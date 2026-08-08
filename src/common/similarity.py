from __future__ import annotations

from rapidfuzz.distance import Levenshtein


def normalized_levenshtein(
    left: str,
    right: str,
    *,
    score_cutoff: float = 0.0,
    **_kwargs,
) -> float:
    score = 100.0 * Levenshtein.normalized_similarity(left, right)
    return score if score >= score_cutoff else 0.0


def token_sort_levenshtein(left: str, right: str) -> float:
    left_sorted = " ".join(sorted(left.split()))
    right_sorted = " ".join(sorted(right.split()))
    return normalized_levenshtein(left_sorted, right_sorted)
