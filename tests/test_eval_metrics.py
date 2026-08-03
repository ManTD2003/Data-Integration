from src.eval.metrics import SetScore, mean, reciprocal_rank


def test_set_score_accumulates_over_records():
    score = SetScore()
    score.update({"python", "sql"}, {"python", "java"})
    score.update({"docker"}, {"docker"})

    assert (score.tp, score.fp, score.fn) == (2, 1, 1)
    assert score.precision == 2 / 3
    assert score.recall == 2 / 3
    assert score.f1 == 2 / 3


def test_set_score_handles_empty_prediction():
    score = SetScore()
    score.update({"python"}, set())
    assert score.precision == 0.0
    assert score.recall == 0.0
    assert score.f1 == 0.0


def test_perfect_prediction_scores_one():
    score = SetScore()
    score.update({"python", "sql"}, {"sql", "python"})
    assert score.f1 == 1.0


def test_reciprocal_rank_uses_first_matching_position():
    assert reciprocal_rank(["a", "b", "c"], "a") == 1.0
    assert reciprocal_rank(["a", "b", "c"], "b") == 0.5
    assert reciprocal_rank(["a", "b", "c"], "z") == 0.0


def test_mean_of_empty_list_is_zero():
    assert mean([]) == 0.0
    assert mean([1.0, 0.0]) == 0.5
