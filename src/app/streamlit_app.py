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


def page_search_jobs(con) -> None:
    st.header("Tìm việc theo kỹ năng")
    skill_id = _select_skill(con, "search")
    if skill_id is None:
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        expand = st.checkbox("Mở rộng phân cấp (gồm cả kỹ năng con)", value=True)
    with col2:
        role_families = ["Tất cả"] + queries.list_role_families(con)
        role_family = st.selectbox("Nhóm nghề", role_families)
        role_family = None if role_family == "Tất cả" else role_family
    with col3:
        cities = ["Tất cả"] + queries.list_cities(con)
        city = st.selectbox("Địa điểm", cities)
        city = None if city == "Tất cả" else city

    jobs = queries.search_jobs(con, skill_id, expand=expand, role_family=role_family, city=city, limit=50)
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
            location = job.get("city") or job.get("location") or "—"
            seniority = job.get("seniority") or "—"
            st.caption(f"{job.get('company') or '—'} · {location} · {seniority} · {job['source']}")
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


def page_dashboard(con) -> None:
    st.header("Thống kê nhu cầu kỹ năng")
    col1, col2 = st.columns(2)
    with col1:
        skill_type = st.selectbox("Loại kỹ năng", ["Tất cả", "hard", "soft"])
        skill_type = None if skill_type == "Tất cả" else skill_type
    with col2:
        role_families = ["Tất cả"] + queries.list_role_families(con)
        role_family = st.selectbox("Nhóm nghề", role_families, key="dash_role")
        role_family = None if role_family == "Tất cả" else role_family

    top = queries.top_skills(con, skill_type=skill_type, role_family=role_family, limit=20)
    if top:
        st.write("Top kỹ năng theo số tin tuyển dụng")
        df = pd.DataFrame(top).set_index("canonical_name")["n"]
        st.bar_chart(df)

    ratio = queries.hard_soft_ratio(con, role_family=role_family)
    if ratio:
        st.write("Số tin có yêu cầu kỹ năng cứng / kỹ năng mềm")
        st.bar_chart(pd.Series(ratio))


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
