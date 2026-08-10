"""Chạy: streamlit run src/app/streamlit_app.py"""

from __future__ import annotations

import sys
from pathlib import Path

# streamlit run thực thi file trực tiếp nên không tự thêm thư mục gốc dự án vào
# sys.path (khác với `python -m src...`) — phải tự thêm để import được package src.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from src.api import queries
from src.app import charts

st.set_page_config(page_title="Tìm kiếm kỹ năng tuyển dụng", layout="wide")


@st.cache_resource
def _connection():
    return queries.get_connection()


def _select_skill(con, key: str) -> str | None:
    query = st.text_input("Nhập tên kỹ năng", key=f"{key}_query")
    if not query:
        return None
    matches = queries.search_skills(con, query, limit=15)
    if not matches:
        st.info("Không tìm thấy kỹ năng nào khớp.")
        return None
    options = {f"{m['canonical_name']} ({m['skill_type']})": m["skill_id"] for m in matches}
    choice = st.selectbox("Chọn kỹ năng", list(options), key=f"{key}_choice")
    return options[choice]


def _location_label(job: dict) -> str:
    """Ưu tiên tỉnh thành đã chuẩn hoá, thiếu thì mới hiện địa chỉ thô của nguồn."""
    parts = [job.get("city"), job.get("country")]
    label = " · ".join(p for p in parts if p)
    return label or job.get("location") or "—"


def page_search_jobs(con) -> None:
    st.header("Tìm việc theo kỹ năng")
    skill_id = _select_skill(con, "search")
    if skill_id is None:
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        expand = st.checkbox("Mở rộng phân cấp (gồm cả kỹ năng con)", value=True)
    with col2:
        countries = ["Tất cả"] + queries.list_countries(con)
        country = st.selectbox("Quốc gia", countries)
        country = None if country == "Tất cả" else country
    with col3:
        cities = ["Tất cả"] + queries.list_cities(con, country=country)
        city = st.selectbox("Tỉnh/thành phố", cities)
        city = None if city == "Tất cả" else city

    jobs = queries.search_jobs(
        con, skill_id, expand=expand, city=city, country=country, limit=50
    )
    st.write(f"{len(jobs)} tin tuyển dụng")
    for job in jobs:
        with st.container(border=True):
            title = job["title_raw"] or "(không có tiêu đề)"
            if job.get("url"):
                st.markdown(f"**[{title}]({job['url']})**")
            elif job.get("source_search_url"):
                # Hai nguồn không phát hành URL tin nên chỉ dẫn về trang tìm kiếm của họ.
                st.markdown(f"**{title}** — [tìm trên nguồn]({job['source_search_url']})")
            else:
                st.markdown(f"**{title}**")
            seniority = job.get("seniority") or "—"
            st.caption(f"{job.get('company') or '—'} · {_location_label(job)} · {seniority} · {job['source']}")
            st.write(f"Kỹ năng khớp: {job['matched_skills']}")


def page_skill_detail(con) -> None:
    st.header("Tra cứu kỹ năng")
    skill_id = _select_skill(con, "lookup")
    if skill_id is None:
        return

    detail = queries.get_skill_detail(con, skill_id)
    st.subheader(detail["canonical_name"])
    st.write("Loại: " + ("Kỹ năng cứng" if detail["skill_type"] == "hard" else "Kỹ năng mềm"))

    if detail["parent"]:
        st.write(f"Thuộc nhóm tổng quát hơn: **{detail['parent']['canonical_name']}**")
    if detail["children"]:
        st.write("Kỹ năng con (cụ thể hơn): " + ", ".join(c["canonical_name"] for c in detail["children"]))
    if detail["variants"]:
        st.write("Biến thể đã gộp về kỹ năng này: " + ", ".join(detail["variants"]))
    st.write(f"Xuất hiện trong **{detail['job_count']}** tin tuyển dụng")

    if detail["evidence_samples"]:
        st.write("Ví dụ trích chọn (provenance):")
        for ev in detail["evidence_samples"]:
            st.caption(
                f"[{ev['source']} · {ev['extraction_method']} · score {ev['confidence']}] {ev['evidence_snippet']}"
            )


def _figure(title: str, chart, rows: list[dict], columns: dict[str, str], note: str | None = None) -> None:
    """Một biểu đồ kèm bảng số liệu tương đương.

    Bảng luôn có để giá trị không bị khoá sau tooltip — người đọc bằng bàn phím hoặc
    không phân biệt được sắc độ vẫn lấy được đúng con số.
    """
    st.subheader(title)
    if note:
        st.caption(note)
    if not rows:
        st.info("Không có dữ liệu trong lát cắt đang chọn.")
        return
    st.altair_chart(chart, use_container_width=True, theme=None)
    with st.expander("Bảng số liệu"):
        df = pd.DataFrame(rows)[list(columns)].rename(columns=columns)
        st.dataframe(df, use_container_width=True, hide_index=True)


def _dashboard_filters(con) -> dict:
    """Một hàng bộ lọc duy nhất, mọi biểu đồ bên dưới vẽ trên cùng lát cắt đó."""
    col1, col2, col3 = st.columns(3)
    with col1:
        skill_type = st.selectbox("Loại kỹ năng", ["Tất cả", "Kỹ năng cứng", "Kỹ năng mềm"])
        skill_type = {"Kỹ năng cứng": "hard", "Kỹ năng mềm": "soft"}.get(skill_type)
    with col2:
        countries = ["Tất cả"] + queries.list_countries(con)
        country = st.selectbox("Quốc gia", countries, key="dash_country")
        country = None if country == "Tất cả" else country
    with col3:
        cities = ["Tất cả"] + queries.list_cities(con, country=country)
        city = st.selectbox("Tỉnh/thành phố", cities, key="dash_city")
        city = None if city == "Tất cả" else city
    return {"skill_type": skill_type, "country": country, "city": city}


def _vn_int(value: float) -> str:
    return f"{int(value):,}".replace(",", ".")


def _tab_overview(con, f: dict, t: dict) -> None:
    stats = queries.corpus_stats(con, **f)
    cols = st.columns(5)
    cols[0].metric("Tin tuyển dụng", _vn_int(stats["n_jobs"]))
    cols[1].metric("Doanh nghiệp", _vn_int(stats["n_companies"]))
    cols[2].metric("Kỹ năng phân biệt", _vn_int(stats["n_skills"]))
    cols[3].metric("Cặp (tin, kỹ năng)", _vn_int(stats["n_pairs"]))
    cols[4].metric("Kỹ năng mỗi tin", f"{stats['skills_per_job']:.1f}")

    rows = queries.top_skills(con, limit=20, **f)
    _figure(
        "Kỹ năng được yêu cầu nhiều nhất",
        charts.top_skills_bar(rows, t),
        rows,
        {"canonical_name": "Kỹ năng", "category": "Lĩnh vực", "skill_type": "Loại", "n": "Số tin"},
    )

def _tab_place(con, f: dict, t: dict) -> None:
    rows = queries.jobs_by_skill_category(con, **f)
    _figure(
        "Nhu cầu theo lĩnh vực kỹ năng",
        charts.skill_category_bar(rows, t),
        rows,
        {"category": "Lĩnh vực", "n": "Số tin"},
        "Lĩnh vực là mức giữa của phân cấp kỹ năng; một tin đòi Python và Java chỉ được "
        "tính một lần cho Ngôn ngữ lập trình.",
    )

    rows = queries.skill_by_city(con, skill_type=f["skill_type"], country=f["country"] or "Việt Nam")
    _figure(
        "Kỹ năng theo tỉnh/thành phố",
        charts.skill_city_heatmap(rows, t),
        rows,
        {"city": "Tỉnh/thành phố", "canonical_name": "Kỹ năng", "n": "Số tin", "pct": "% tin của tỉnh"},
        "Mỗi ô là tỉ lệ tin của chính tỉnh đó có đòi kỹ năng, không phải số tuyệt đối — "
        "để các tỉnh ít tin vẫn so được với TP HCM và Hà Nội.",
    )

def _tab_relations(con, f: dict, t: dict) -> None:
    rows = queries.skill_cooccurrence(con, **f)
    _figure(
        "Kỹ năng thường được đòi cùng nhau",
        charts.cooccurrence_heatmap(rows, t),
        [r for r in rows if r["skill_a"] != r["skill_b"]],
        {"skill_a": "Kỹ năng", "skill_b": "Đi kèm", "n": "Số tin cùng đòi"},
        "Ma trận đối xứng trên 12 kỹ năng phổ biến nhất của lát cắt. Đường chéo bị bỏ vì "
        "số tin đòi chính kỹ năng đó lớn hơn hẳn mọi ô còn lại và sẽ nuốt hết dải màu.",
    )


def _tab_sources(con, f: dict, t: dict) -> None:
    rows = queries.extraction_method_by_source(con)
    _figure(
        "Cách trích chọn kỹ năng theo nguồn",
        charts.extraction_method_bar(rows, t),
        rows,
        {"source": "Nguồn", "extraction_method": "Cách trích chọn", "n": "Số cặp"},
        "itviec và data_jobs phát hành sẵn nhãn kỹ năng nên dùng thẳng; vieclam24h chỉ có "
        "văn bản mô tả nên phải đối sánh từ điển. Biểu đồ này không theo bộ lọc bên trên.",
    )

    rows = queries.jobs_by_month(con, city=f["city"], country=f["country"])
    _figure(
        "Tin đăng theo tháng",
        charts.jobs_by_month_line(rows, t),
        rows,
        {"month": "Tháng", "source": "Nguồn", "n": "Số tin"},
        "Mười hai tháng gần nhất tính theo ngày đăng của tin. Hình dạng phản ánh cả thời "
        "điểm cào lẫn nhịp tuyển dụng thật; data_jobs là bản trích năm 2023 nên không "
        "xuất hiện trong khoảng này.",
    )


def page_dashboard(con) -> None:
    st.header("Thống kê nhu cầu kỹ năng")
    filters = _dashboard_filters(con)
    tokens = charts.tokens(st.get_option("theme.base"))

    tabs = st.tabs(["Tổng quan", "Lĩnh vực & địa điểm", "Quan hệ kỹ năng", "Nguồn dữ liệu"])
    with tabs[0]:
        _tab_overview(con, filters, tokens)
    with tabs[1]:
        _tab_place(con, filters, tokens)
    with tabs[2]:
        _tab_relations(con, filters, tokens)
    with tabs[3]:
        _tab_sources(con, filters, tokens)


def main() -> None:
    con = _connection()
    page = st.sidebar.radio("Chức năng", ["Tìm việc theo kỹ năng", "Tra cứu kỹ năng", "Dashboard"])
    if page == "Tìm việc theo kỹ năng":
        page_search_jobs(con)
    elif page == "Tra cứu kỹ năng":
        page_skill_detail(con)
    else:
        page_dashboard(con)


main()
