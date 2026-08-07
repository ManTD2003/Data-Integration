"""Các biểu đồ Altair của dashboard.

Tách khỏi `streamlit_app.py` để file kia chỉ còn phần bố cục. Mọi biểu đồ nhận vào
list[dict] do `src.api.queries` trả về và trả ra `alt.Chart`, nên vẽ được mà không
cần kết nối DuckDB — test dựng dữ liệu mẫu là chạy được.

Quy ước màu: một chuỗi số liệu thì dùng đúng một màu (slot 1), không tô đậm nhạt
theo giá trị vì độ dài cột đã nói lên điều đó; nhiều chuỗi thì lấy lần lượt các slot
theo đúng thứ tự đã định, không xoay vòng; thang liên tục (heatmap) dùng một tông
xanh từ nhạt tới đậm. Chữ luôn mang màu chữ, không mang màu của chuỗi.
"""

from __future__ import annotations

import altair as alt

FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

LIGHT = {
    "surface": "#fcfcfb",
    "text": "#0b0b0b",
    "text_secondary": "#52514e",
    "muted": "#898781",
    "grid": "#e1e0d9",
    "axis": "#c3c2b7",
    "series": ["#2a78d6", "#eb6834", "#1baf7a"],
    # Thang liên tục chạy từ bước gần màu nền nhất tới bước xa nhất, để "giá trị lớn"
    # luôn là "nổi khỏi nền": nền sáng thì càng lớn càng đậm, nền tối thì ngược lại.
    "ramp": ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#2a78d6", "#1c5cab", "#104281"],
    # Chữ đặt trong ô màu chọn theo độ đậm của chính ô, không theo nền trang.
    "cell_text_low": "#52514e",
    "cell_text_high": "#ffffff",
}

DARK = {
    "surface": "#1a1a19",
    "text": "#ffffff",
    "text_secondary": "#c3c2b7",
    "muted": "#898781",
    "grid": "#2c2c2a",
    "axis": "#383835",
    "series": ["#3987e5", "#d95926", "#199e70"],
    "ramp": ["#104281", "#1c5cab", "#2a78d6", "#3987e5", "#6da7ec", "#9ec5f4", "#cde2fb"],
    "cell_text_low": "#c3c2b7",
    "cell_text_high": "#0b0b0b",
}

BAR_SIZE = 16
CORNER = 4
LABEL_LIMIT = 220

# Vega-Embed đọc khối này để đổi dấu phân cách số; không có nó thì trục và tooltip in
# "1,234" trong khi phần còn lại của app in "1.234".
VN_LOCALE = {
    "embedOptions": {
        "formatLocale": {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " ₫"]}
    }
}


def tokens(theme_base: str | None) -> dict:
    return DARK if theme_base == "dark" else LIGHT


def _order_by_total(rows: list[dict], key: str, value: str = "n") -> list[str]:
    """Thứ tự hạng mục theo tổng giá trị, tính sẵn ở Python.

    `sort="-x"` của Vega chỉ sắp được khi mỗi hạng mục có đúng một mốc; biểu đồ cột
    nhóm có hai cột trên một hạng mục nên phải truyền thứ tự tường minh.
    """
    totals: dict[str, float] = {}
    for row in rows:
        totals[row[key]] = totals.get(row[key], 0) + row[value]
    return sorted(totals, key=lambda k: -totals[k])


def _style(chart: alt.Chart, t: dict, x_grid: bool = True) -> alt.Chart:
    """Lưới và trục lùi về sau, chữ mang màu chữ, khung view không viền."""
    return (
        chart.properties(usermeta=VN_LOCALE)
        .configure_view(strokeWidth=0, fill=t["surface"])
        .configure_axis(
            labelFont=FONT,
            titleFont=FONT,
            labelColor=t["muted"],
            titleColor=t["text_secondary"],
            labelFontSize=12,
            titleFontSize=12,
            labelLimit=LABEL_LIMIT,
            domainColor=t["axis"],
            tickColor=t["axis"],
            grid=False,
        )
        .configure_axisX(grid=x_grid, gridColor=t["grid"], gridWidth=1, gridOpacity=1, tickCount=6)
        .configure_legend(
            labelFont=FONT,
            titleFont=FONT,
            labelColor=t["text_secondary"],
            titleColor=t["text_secondary"],
            labelFontSize=12,
            titleFontSize=12,
            symbolType="square",
            orient="top",
            direction="horizontal",
            offset=8,
        )
        .configure_text(font=FONT)
    )


def _series_scale(domain: list[str], t: dict) -> alt.Scale:
    """Màu gắn với chính chuỗi số liệu, không gắn với thứ hạng hiện tại.

    Truyền domain tường minh để lọc bớt một chuỗi không làm các chuỗi còn lại đổi màu.
    """
    return alt.Scale(domain=domain, range=t["series"][: len(domain)])


def top_skills_bar(rows: list[dict], t: dict) -> alt.Chart:
    base = alt.Chart(alt.Data(values=rows))
    y = alt.Y("canonical_name:N", sort="-x", title=None)
    bars = base.mark_bar(
        size=BAR_SIZE, cornerRadiusTopRight=CORNER, cornerRadiusBottomRight=CORNER, color=t["series"][0]
    ).encode(
        x=alt.X("n:Q", title="Số tin tuyển dụng", axis=alt.Axis(format=",d")),
        y=y,
        tooltip=[
            alt.Tooltip("canonical_name:N", title="Kỹ năng"),
            alt.Tooltip("category:N", title="Lĩnh vực"),
            alt.Tooltip("n:Q", title="Số tin", format=",d"),
        ],
    )
    labels = base.mark_text(align="left", dx=6, fontSize=11, color=t["text_secondary"]).encode(
        x="n:Q", y=y, text=alt.Text("n:Q", format=",d")
    )
    return _style((bars + labels).properties(height=alt.Step(24)), t)


def skill_type_grouped_bar(rows: list[dict], t: dict) -> alt.Chart:
    """Cột nhóm chứ không chồng: một tin đòi cả hai loại được đếm ở cả hai cột, chồng
    lên nhau thì tổng vượt quá số tin của nhóm nghề."""
    labels = {"hard": "Kỹ năng cứng", "soft": "Kỹ năng mềm"}
    rows = [dict(r, loai=labels.get(r["skill_type"], r["skill_type"])) for r in rows]
    domain = [labels["hard"], labels["soft"]]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(size=12, cornerRadiusTopRight=CORNER, cornerRadiusBottomRight=CORNER)
        .encode(
            x=alt.X("n:Q", title="Số tin tuyển dụng", axis=alt.Axis(format=",d")),
            y=alt.Y("role_family:N", sort=_order_by_total(rows, "role_family"), title=None),
            yOffset=alt.YOffset("loai:N", sort=domain),
            color=alt.Color("loai:N", scale=_series_scale(domain, t), title=None),
            tooltip=[
                alt.Tooltip("role_family:N", title="Nhóm nghề"),
                alt.Tooltip("loai:N", title="Loại"),
                alt.Tooltip("n:Q", title="Số tin", format=",d"),
            ],
        )
        .properties(height=alt.Step(32))
    )
    return _style(chart, t)


def skill_category_bar(rows: list[dict], t: dict) -> alt.Chart:
    base = alt.Chart(alt.Data(values=rows))
    y = alt.Y("category:N", sort="-x", title=None)
    bars = base.mark_bar(
        size=BAR_SIZE, cornerRadiusTopRight=CORNER, cornerRadiusBottomRight=CORNER, color=t["series"][0]
    ).encode(
        x=alt.X("n:Q", title="Số tin có ít nhất một kỹ năng thuộc lĩnh vực", axis=alt.Axis(format=",d")),
        y=y,
        tooltip=[
            alt.Tooltip("category:N", title="Lĩnh vực"),
            alt.Tooltip("n:Q", title="Số tin", format=",d"),
        ],
    )
    labels = base.mark_text(align="left", dx=6, fontSize=11, color=t["text_secondary"]).encode(
        x="n:Q", y=y, text=alt.Text("n:Q", format=",d")
    )
    return _style((bars + labels).properties(height=alt.Step(24)), t)


def _heatmap(
    rows: list[dict],
    t: dict,
    x_field: str,
    y_field: str,
    value_field: str,
    x_order: list[str],
    y_order: list[str],
    legend_title: str,
    value_format: str,
    tooltip: list[alt.Tooltip],
    label_cutoff: float,
    label_angle: int = 0,
) -> alt.Chart:
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X(
            f"{x_field}:N",
            sort=x_order,
            title=None,
            axis=alt.Axis(labelAngle=label_angle, labelLimit=LABEL_LIMIT, labelAlign="right" if label_angle else "center"),
        ),
        y=alt.Y(f"{y_field}:N", sort=y_order, title=None),
    )
    cells = base.mark_rect(stroke=t["surface"], strokeWidth=2).encode(
        color=alt.Color(
            f"{value_field}:Q",
            scale=alt.Scale(range=t["ramp"]),
            legend=alt.Legend(title=legend_title, gradientLength=140),
        ),
        tooltip=tooltip,
    )
    labels = base.mark_text(fontSize=11).encode(
        text=alt.Text(f"{value_field}:Q", format=value_format),
        color=alt.condition(
            alt.datum[value_field] >= label_cutoff,
            alt.value(t["cell_text_high"]),
            alt.value(t["cell_text_low"]),
        ),
    )
    return _style((cells + labels).properties(height=alt.Step(26)), t, x_grid=False)


def skill_city_heatmap(rows: list[dict], t: dict) -> alt.Chart:
    """Tỉ lệ tin trong từng tỉnh có đòi kỹ năng, không phải số tuyệt đối.

    Đếm tuyệt đối thì TP HCM và Hà Nội nuốt hết dải màu, các tỉnh còn lại thành một
    mảng nhạt như nhau và không so được với nhau.
    """
    cities = list(dict.fromkeys(r["city"] for r in rows))
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["canonical_name"]] = totals.get(r["canonical_name"], 0) + r["n"]
    skills = sorted(totals, key=lambda k: -totals[k])
    cutoff = max((r["pct"] for r in rows), default=0) * 0.6

    return _heatmap(
        rows,
        t,
        x_field="city",
        y_field="canonical_name",
        value_field="pct",
        x_order=cities,
        y_order=skills,
        legend_title="% số tin của tỉnh",
        value_format=".0f",
        tooltip=[
            alt.Tooltip("city:N", title="Tỉnh/thành phố"),
            alt.Tooltip("canonical_name:N", title="Kỹ năng"),
            alt.Tooltip("n:Q", title="Số tin", format=",d"),
            alt.Tooltip("pct:Q", title="% tin của tỉnh", format=".1f"),
        ],
        label_cutoff=cutoff,
    )


def cooccurrence_heatmap(rows: list[dict], t: dict) -> alt.Chart:
    """Ma trận số tin cùng đòi hai kỹ năng.

    Bỏ đường chéo: số tin đòi chính kỹ năng đó lớn hơn hẳn mọi ô còn lại, giữ lại thì
    toàn bộ dải màu dồn vào đường chéo và các cặp thật sự không phân biệt được.
    """
    totals = {r["skill_a"]: r["n"] for r in rows if r["skill_a"] == r["skill_b"]}
    order = sorted(totals, key=lambda k: -totals[k])
    pairs = [r for r in rows if r["skill_a"] != r["skill_b"]]
    cutoff = max((r["n"] for r in pairs), default=0) * 0.6

    return _heatmap(
        pairs,
        t,
        x_field="skill_a",
        y_field="skill_b",
        value_field="n",
        x_order=order,
        y_order=order,
        legend_title="Số tin",
        value_format=",d",
        tooltip=[
            alt.Tooltip("skill_a:N", title="Kỹ năng"),
            alt.Tooltip("skill_b:N", title="Đi kèm"),
            alt.Tooltip("n:Q", title="Số tin cùng đòi", format=",d"),
        ],
        label_cutoff=cutoff,
        # Tên kỹ năng tiếng Việt dài, để ngang thì các nhãn trục dưới đè lên nhau.
        label_angle=-40,
    )


def salary_band_bar(rows: list[dict], t: dict) -> alt.Chart:
    """Khoảng lương trung vị: mỗi nhóm nghề một đoạn từ mức sàn tới mức trần."""
    rows = [
        dict(r, low_m=r["low"] / 1e6, high_m=r["high"] / 1e6, band=f"{r['low'] / 1e6:g}–{r['high'] / 1e6:g}")
        for r in rows
    ]
    base = alt.Chart(alt.Data(values=rows))
    y = alt.Y("role_family:N", sort=alt.EncodingSortField("high_m", order="descending"), title=None)
    band = base.mark_bar(
        size=10, cornerRadius=CORNER, color=t["series"][0], opacity=0.85
    ).encode(
        x=alt.X("low_m:Q", title="Triệu VNĐ / tháng", scale=alt.Scale(zero=True)),
        x2="high_m:Q",
        y=y,
        tooltip=[
            alt.Tooltip("role_family:N", title="Nhóm nghề"),
            alt.Tooltip("low_m:Q", title="Sàn (trung vị)", format=".1f"),
            alt.Tooltip("high_m:Q", title="Trần (trung vị)", format=".1f"),
            alt.Tooltip("n:Q", title="Số tin có lương", format=",d"),
        ],
    )
    labels = base.mark_text(align="left", dx=8, fontSize=11, color=t["text_secondary"]).encode(
        x="high_m:Q", y=y, text="band:N"
    )
    return _style((band + labels).properties(height=alt.Step(26)), t)


def extraction_method_bar(rows: list[dict], t: dict) -> alt.Chart:
    """Cột chồng: mỗi nguồn được chia theo cách trích chọn ra cặp (tin, kỹ năng)."""
    labels = {
        "source_provided": "Nhãn sẵn của nguồn",
        "exact_match": "Đối sánh gazetteer",
        "fuzzy_match": "Đối sánh xấp xỉ",
    }
    domain = [labels["source_provided"], labels["exact_match"], labels["fuzzy_match"]]
    rows = [dict(r, cach=labels.get(r["extraction_method"], r["extraction_method"])) for r in rows]
    chart = (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(size=22, stroke=t["surface"], strokeWidth=2)
        .encode(
            x=alt.X("n:Q", title="Số cặp (tin, kỹ năng)", axis=alt.Axis(format=",d")),
            y=alt.Y("source:N", sort="-x", title=None),
            color=alt.Color("cach:N", scale=_series_scale(domain, t), sort=domain, title=None),
            order=alt.Order("color_cach_sort_index:Q"),
            tooltip=[
                alt.Tooltip("source:N", title="Nguồn"),
                alt.Tooltip("cach:N", title="Cách trích chọn"),
                alt.Tooltip("n:Q", title="Số cặp", format=",d"),
            ],
        )
        .properties(height=alt.Step(46))
    )
    return _style(chart, t)


def jobs_by_month_line(rows: list[dict], t: dict) -> alt.Chart:
    sources = sorted({r["source"] for r in rows})
    color = alt.Color("source:N", scale=_series_scale(sources, t), title=None)
    base = alt.Chart(alt.Data(values=rows)).encode(
        x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("n:Q", title="Số tin đăng", axis=alt.Axis(format=",d")),
        color=color,
    )
    # Nội suy thẳng: số tin là giá trị rời rạc theo tháng, đường cong sẽ vẽ ra những
    # mức không có thật ở giữa hai mốc.
    line = base.mark_line(strokeWidth=2)
    dots = base.mark_point(size=70, filled=True, stroke=t["surface"], strokeWidth=2).encode(
        tooltip=[
            alt.Tooltip("month:N", title="Tháng"),
            alt.Tooltip("source:N", title="Nguồn"),
            alt.Tooltip("n:Q", title="Số tin", format=",d"),
        ]
    )
    return _style((line + dots).properties(height=280), t, x_grid=False)
