"""Giao diện gán nhãn manual gold cho skill extraction."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from src.eval.annotation import (
    ANNOTATIONS_PATH,
    MANIFEST_PATH,
    TASKS_PATH,
    load_skill_dictionary,
    read_jsonl,
    save_annotation,
)

st.set_page_config(page_title="Gán nhãn skill extraction", layout="wide")


@st.cache_data
def load_tasks() -> list[dict]:
    return sorted(read_jsonl(TASKS_PATH), key=lambda task: task["order"])


@st.cache_data
def skill_options() -> tuple[dict[str, str], dict[str, str]]:
    skill_dict = load_skill_dictionary()
    label_to_id: dict[str, str] = {}
    id_to_label: dict[str, str] = {}
    for skill in sorted(
        skill_dict.skills.values(), key=lambda item: item["canonical_name"].casefold()
    ):
        aliases = [
            alias
            for alias in skill["aliases"]
            if alias.casefold() != skill["canonical_name"].casefold()
        ]
        suffix = f" — {', '.join(aliases[:4])}" if aliases else ""
        label = f"{skill['canonical_name']} ({skill['skill_type']}){suffix}"
        label_to_id[label] = skill["skill_id"]
        id_to_label[skill["skill_id"]] = label
    return label_to_id, id_to_label


def annotation_map() -> dict[str, dict]:
    return {row["task_id"]: row for row in read_jsonl(ANNOTATIONS_PATH)}


def show_field(label: str, value: str | None, height: int) -> None:
    with st.expander(label, expanded=True):
        st.text_area(
            label,
            value=value or "(trống)",
            height=height,
            disabled=True,
            label_visibility="collapsed",
        )


tasks = load_tasks()
if not tasks:
    st.error("Chưa có batch gán nhãn. Chạy `./run.sh annotate init` trước.")
    st.stop()

labels, id_to_label = skill_options()
annotations = annotation_map()
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
test_frozen = bool(manifest.get("test_frozen"))

st.title("Gán nhãn skill extraction")
st.caption(
    "Chỉ chọn kỹ năng được nhắc trực tiếp trong tiêu đề, yêu cầu hoặc mô tả. "
    "Không suy diễn từ chức danh và không tra source tags."
)

annotator = st.sidebar.text_input("Người gán nhãn")
source_filter = st.sidebar.selectbox("Nguồn", ["Tất cả", "itviec", "vieclam24h"])
split_options = ["test", "development", "Tất cả"] if test_frozen else ["development"]
split_filter = st.sidebar.selectbox("Split", split_options)
status_filter = st.sidebar.selectbox(
    "Trạng thái", ["Chưa hoàn thành", "Tất cả", "Đã hoàn thành"]
)

complete_count = sum(
    annotations.get(task["task_id"], {}).get("status") == "complete" for task in tasks
)
st.sidebar.progress(
    complete_count / len(tasks), text=f"{complete_count}/{len(tasks)} task hoàn thành"
)
if not test_frozen:
    st.sidebar.info(
        "Test split đang ẩn. Hoàn thành development split rồi chạy "
        "`./run.sh annotate freeze`."
    )

filtered = []
for task in tasks:
    status = annotations.get(task["task_id"], {}).get("status", "unlabeled")
    if source_filter != "Tất cả" and task["source"] != source_filter:
        continue
    if split_filter != "Tất cả" and task["split"] != split_filter:
        continue
    if status_filter == "Chưa hoàn thành" and status == "complete":
        continue
    if status_filter == "Đã hoàn thành" and status != "complete":
        continue
    filtered.append(task)

if not annotator.strip():
    st.info("Nhập tên người gán nhãn ở thanh bên để bắt đầu.")
    st.stop()
if not filtered:
    st.success("Không còn task nào trong bộ lọc hiện tại.")
    st.stop()

task_labels = {
    f"{task['order']:03d} · {task['source']} · {task['fields']['title']}": task
    for task in filtered
}
selected_label = st.selectbox("Tin cần gán nhãn", list(task_labels))
task = task_labels[selected_label]
current = annotations.get(task["task_id"], {})

left, right = st.columns([3, 2])
with left:
    st.subheader(task["fields"]["title"] or "(không có tiêu đề)")
    metadata = [task["source"], task["split"], task["length_band"]]
    if task.get("company"):
        metadata.append(task["company"])
    st.caption(" · ".join(metadata))
    if task.get("url"):
        st.link_button("Mở tin gốc", task["url"])
    show_field("Yêu cầu", task["fields"].get("requirements_raw"), 260)
    show_field("Mô tả", task["fields"].get("description"), 360)

with right:
    st.subheader("Nhãn")
    defaults = [
        id_to_label[skill_id]
        for skill_id in current.get("skill_ids", [])
        if skill_id in id_to_label
    ]
    with st.form(f"annotation-{task['task_id']}"):
        selected_skills = st.multiselect(
            "Canonical skills",
            list(labels),
            default=defaults,
            help="Có thể tìm bằng canonical name hoặc alias hiển thị trong danh sách.",
        )
        unresolved = st.text_area(
            "Kỹ năng chưa có trong dictionary",
            value="\n".join(current.get("unresolved_terms", [])),
            help=(
                "Mỗi dòng một canonical name. Các mục này vẫn thuộc gold và sẽ đo "
                "dictionary coverage."
            ),
        )
        notes = st.text_area("Ghi chú", value=current.get("notes", ""))
        complete = st.checkbox(
            "Đã kiểm tra toàn bộ tin", value=current.get("status") == "complete"
        )
        submitted = st.form_submit_button("Lưu nhãn", type="primary")

    if submitted:
        unresolved_terms = [term.strip() for term in unresolved.splitlines() if term.strip()]
        save_annotation(
            {
                "task_id": task["task_id"],
                "annotator": annotator.strip(),
                "status": "complete" if complete else "draft",
                "skill_ids": sorted({labels[label] for label in selected_skills}),
                "unresolved_terms": unresolved_terms,
                "notes": notes.strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        st.cache_data.clear()
        st.rerun()
