import pytest

from src.common.similarity import normalized_levenshtein, token_sort_levenshtein


def test_normalized_levenshtein_uses_zero_to_one_hundred_scale():
    assert normalized_levenshtein("autocard", "autocad") == pytest.approx(87.5)


def test_token_sort_levenshtein_ignores_token_order():
    assert token_sort_levenshtein("abc ha noi", "ha noi abc") == 100.0
