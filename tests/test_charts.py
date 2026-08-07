from src.app import charts

TOP_SKILLS = [
    {"canonical_name": "Python", "category": "Ngôn ngữ lập trình", "skill_type": "hard", "n": 90},
    {"canonical_name": "SQL", "category": "Cơ sở dữ liệu", "skill_type": "hard", "n": 60},
]

BY_FAMILY = [
    {"role_family": "Kế toán", "skill_type": "hard", "n": 10},
    {"role_family": "Kế toán", "skill_type": "soft", "n": 8},
    {"role_family": "Kỹ sư dữ liệu", "skill_type": "hard", "n": 30},
    {"role_family": "Kỹ sư dữ liệu", "skill_type": "soft", "n": 1},
]

BY_CITY = [
    {"city": "TP Hồ Chí Minh", "canonical_name": "Python", "n": 40, "city_total": 100, "pct": 40.0},
    {"city": "TP Hồ Chí Minh", "canonical_name": "SQL", "n": 20, "city_total": 100, "pct": 20.0},
    {"city": "Hà Nội", "canonical_name": "Python", "n": 5, "city_total": 20, "pct": 25.0},
    {"city": "Hà Nội", "canonical_name": "SQL", "n": 9, "city_total": 20, "pct": 45.0},
]

COOCCURRENCE = [
    {"skill_a": "Python", "skill_b": "Python", "n": 90},
    {"skill_a": "SQL", "skill_b": "SQL", "n": 60},
    {"skill_a": "Python", "skill_b": "SQL", "n": 25},
    {"skill_a": "SQL", "skill_b": "Python", "n": 25},
]

SALARY = [
    {"role_family": "Kỹ sư phần mềm", "n": 12, "low": 15_000_000.0, "high": 20_000_000.0},
    {"role_family": "Kế toán", "n": 30, "low": 10_000_000.0, "high": 15_000_000.0},
]


def _spec(chart) -> dict:
    """to_dict() ném lỗi nếu encoding sai, nên gọi nó cũng là một phép kiểm tra."""
    return chart.to_dict()


def _layers(spec: dict) -> list[dict]:
    return spec.get("layer", [spec])


def _values(spec: dict) -> list[dict]:
    for layer in _layers(spec):
        data = layer.get("data") or spec.get("data")
        if data and "values" in data:
            return data["values"]
    return []


def test_tokens_pick_the_dark_set_only_for_dark_base():
    assert charts.tokens("dark") is charts.DARK
    assert charts.tokens("light") is charts.LIGHT
    assert charts.tokens(None) is charts.LIGHT


def test_sequential_ramp_runs_away_from_the_surface_in_both_modes():
    """Giá trị lớn phải là màu xa nền nhất; nền tối mà vẫn dùng thang nhạt-tới-đậm thì
    ô giá trị thấp lại là ô sáng nhất và biểu đồ đọc ngược."""
    assert charts.LIGHT["ramp"][0] == charts.DARK["ramp"][-1]
    assert charts.LIGHT["ramp"][-1] == charts.DARK["ramp"][0]


def test_every_chart_builds_a_valid_spec():
    t = charts.tokens("light")
    built = [
        charts.top_skills_bar(TOP_SKILLS, t),
        charts.skill_type_grouped_bar(BY_FAMILY, t),
        charts.skill_category_bar([{"category": "Cơ sở dữ liệu", "n": 5}], t),
        charts.skill_city_heatmap(BY_CITY, t),
        charts.cooccurrence_heatmap(COOCCURRENCE, t),
        charts.salary_band_bar(SALARY, t),
        charts.extraction_method_bar([{"source": "itviec", "extraction_method": "source_provided", "n": 7}], t),
        charts.jobs_by_month_line([{"month": "2026-07", "source": "itviec", "n": 4}], t),
    ]
    for chart in built:
        assert _spec(chart)


def test_grouped_bar_sorts_families_by_total_not_by_first_row():
    spec = _spec(charts.skill_type_grouped_bar(BY_FAMILY, charts.tokens("light")))
    assert spec["encoding"]["y"]["sort"] == ["Kỹ sư dữ liệu", "Kế toán"]


def test_cooccurrence_drops_the_diagonal():
    """Số tin đòi chính kỹ năng đó lớn hơn hẳn mọi cặp, giữ lại thì nuốt hết dải màu."""
    spec = _spec(charts.cooccurrence_heatmap(COOCCURRENCE, charts.tokens("light")))
    pairs = _values(spec)
    assert all(row["skill_a"] != row["skill_b"] for row in pairs)
    assert len(pairs) == 2


def test_cooccurrence_orders_both_axes_by_the_diagonal():
    spec = _spec(charts.cooccurrence_heatmap(COOCCURRENCE, charts.tokens("light")))
    encoding = _layers(spec)[0]["encoding"]
    assert encoding["x"]["sort"] == encoding["y"]["sort"] == ["Python", "SQL"]


def test_salary_band_labels_show_both_ends_in_millions():
    spec = _spec(charts.salary_band_bar(SALARY, charts.tokens("light")))
    assert {row["band"] for row in _values(spec)} == {"15–20", "10–15"}


def test_charts_declare_the_vietnamese_number_locale():
    spec = _spec(charts.top_skills_bar(TOP_SKILLS, charts.tokens("light")))
    assert spec["usermeta"]["embedOptions"]["formatLocale"]["thousands"] == "."
