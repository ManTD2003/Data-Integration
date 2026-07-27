"""Xây phân cấp kỹ năng cụ thể -> tổng quát (VD: Python/Java là con của "Ngôn ngữ
lập trình"). Nguồn dữ liệu tuyển dụng không tự cho biết quan hệ cha/con nên phần
này dựa vào phân loại lĩnh vực đã soát thủ công qua toàn bộ từ điển sau khi gộp
biến thể (resolve_variants.py) — cách tiếp cận "chỉ dựa nền có sẵn, bổ sung nhánh
thiếu" đã nêu trong kế hoạch, thay vì suy luận hypernym tự động (rủi ro sai cao
với quy mô từ điển ~370 mục).

Mỗi nhóm là một skill mới (skill_type "hard", trừ "Kỹ năng mềm") đóng vai trò nút
cha; toàn bộ skill thuộc lĩnh vực khác (không nêu tên) vẫn giữ nguyên không có cha,
việc này chấp nhận được vì hierarchy không bắt buộc phủ hết 100%.
"""

from __future__ import annotations

import json

from src.common.paths import STAGING
from src.process.skill_dictionary import DICTIONARY_PATH, SkillDictionary

CLOSURE_PATH = STAGING / "skill_closure.jsonl"

CATEGORY_MAP: dict[str, list[str]] = {
    "Ngôn ngữ lập trình": [
        "Python", "Java", "JavaScript", "TypeScript", "PHP", "go", "C#", "C++", "c",
        "Kotlin", "Swift", "rust", "scala", "r", "Dart", "Objective C", "groovy",
        "perl", "lua", "julia", "matlab", "cobol", "fortran", "assembly", "solidity",
        "f#", "apl", "Embedded C",
    ],
    "Cơ sở dữ liệu": [
        "MySQL", "PostgreSql", "MongoDB", "Oracle", "sql server", "redis", "cassandra",
        "dynamodb", "mariadb", "db2", "IBM DB2", "neo4j", "couchbase", "elasticsearch",
        "NoSQL", "SQL", "t-sql",
    ],
    "Điện toán đám mây": [
        "AWS", "Azure", "GCP", "Google Cloud", "ibm cloud", "openstack", "aurora",
        "Amazon RDS", "Snowflake", "databricks", "redshift", "bigquery",
        "AWS CloudFormation", "AWS Glue", "AWS Lambda",
    ],
    "Phát triển Frontend": [
        "react", "vue", "Angular", "NextJS", "jquery", "Blazor", "HTML", "HTML5",
        "CSS", "sass",
    ],
    "Phát triển Backend": [
        "node", "Django", "flask", "FastAPI", "express", "Spring", "Spring Boot",
        "laravel", "Ruby on Rails", "symfony", ".NET", ".Net Core", "ASP.NET", "J2EE",
    ],
    "DevOps & CI/CD": [
        "Docker", "Kubernetes", "Jenkins", "GitLab CI", "GitHub Actions", "Ansible",
        "Terraform", "puppet", "chef", "CI/CD",
    ],
    "Kiểm thử phần mềm": [
        "Selenium", "Playwright", "JUnit", "Appium", "Automation Test", "Tester", "QA QC",
    ],
    "Phân tích dữ liệu & BI": [
        "Power BI", "Tableau", "qlik", "Looker", "microstrategy", "cognos", "spss",
        "Business Intelligence", "Data Analysis", "alteryx", "datarobot", "dax",
        "rshiny", "tidyverse", "ggplot2",
    ],
    "Machine Learning & AI": [
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "scikit-learn",
        "keras", "Computer Vision", "nltk", "LLM", "Prompt Engineering", "mxnet",
        "theano", "Data Science", "AI",
    ],
    "Thiết kế đồ hoạ": [
        "Adobe Photoshop", "Adobe Illustrator", "Adobe Premiere", "CorelDRAW", "Figma",
        "UI-UX", "Visual Design",
    ],
    "Ngoại ngữ": ["English", "Tiếng Trung", "Japanese", "Korean"],
    "Tin học văn phòng": [
        "excel", "word", "powerpoint", "VBA", "outlook", "sheets", "spreadsheet", "ms access",
    ],
    "An ninh mạng": [
        "Cybersecurity", "Information Security", "Application Security", "Cloud Security",
        "Firewall", "SIEM", "SOAR", "Identity & Access Management",
        "Encryption Key Management", "ISO 27001", "CompTIA Security+", "EDR",
        "Web Application Firewall", "Security", "Security Awareness Training",
        "Incident Response", "Pentest",
    ],
    "Kế toán": ["Kế toán công nợ", "Kế toán thuế", "Phần mềm kế toán MISA"],
    "Marketing & Bán hàng": [
        "Bán hàng", "Chăm sóc khách hàng", "Telesale", "Content Marketing",
        "Digital Marketing", "Social Media Marketing", "Quảng cáo Facebook",
        "Quảng cáo Google", "SEO", "CRM", "Presale",
    ],
    "Quản lý dự án": [
        "Project Management", "Lean Project Management", "Scrum", "Agile",
        "Waterfall Methodology", "User story", "Product Owner", "Product Management",
        "Product roadmap", "Product strategy", "Product Design", "Product Metrics",
    ],
    "Xây dựng": [
        "Giám sát công trình", "Dự toán xây dựng", "Đọc bản vẽ kỹ thuật", "AutoCAD",
    ],
    "Nhân sự": ["Tuyển dụng", "Tính lương, C&B"],
}

SOFT_SKILL_ROOT = "Kỹ năng mềm"


def assign_parents(skill_dict: SkillDictionary) -> list[str]:
    """Gán parent_skill_id theo CATEGORY_MAP. Trả về danh sách tên không tìm thấy
    trong từ điển (để phát hiện lỗi gõ tên trước khi commit)."""
    missing: list[str] = []
    for category_name, children in CATEGORY_MAP.items():
        category_id = skill_dict.add(category_name, "hard", [category_name])
        for child_name in children:
            entry = skill_dict.lookup(child_name)
            if entry is None:
                missing.append(child_name)
                continue
            if entry["skill_id"] == category_id:
                continue
            entry["parent_skill_id"] = category_id

    soft_root_id = skill_dict.add(SOFT_SKILL_ROOT, "soft", [SOFT_SKILL_ROOT])
    for entry in skill_dict.skills.values():
        if entry["skill_type"] == "soft" and entry["skill_id"] != soft_root_id and not entry["parent_skill_id"]:
            entry["parent_skill_id"] = soft_root_id

    return missing


def build_closure(skill_dict: SkillDictionary) -> list[dict]:
    rows = [{"ancestor_id": sid, "descendant_id": sid, "depth": 0} for sid in skill_dict.skills]
    for entry in skill_dict.skills.values():
        parent_id = entry["parent_skill_id"]
        if parent_id:
            rows.append({"ancestor_id": parent_id, "descendant_id": entry["skill_id"], "depth": 1})
    return rows


def run() -> str:
    skills = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    skill_dict = SkillDictionary()
    for entry in skills:
        entry.setdefault("parent_skill_id", None)
        skill_dict.skills[entry["skill_id"]] = entry
        for alias in entry["aliases"]:
            skill_dict.alias_index[alias] = entry["skill_id"]

    missing = assign_parents(skill_dict)
    if missing:
        print("Không tìm thấy trong từ điển (bỏ qua):", missing)

    DICTIONARY_PATH.write_text(
        json.dumps(skill_dict.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    closure = build_closure(skill_dict)
    with open(CLOSURE_PATH, "w", encoding="utf-8") as f:
        for row in closure:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with_parent = sum(1 for e in skill_dict.skills.values() if e["parent_skill_id"])
    print(f"Skills: {len(skill_dict.skills)} | có parent: {with_parent} | closure rows: {len(closure)}")
    print(f"Từ điển (đã gắn phân cấp) -> {DICTIONARY_PATH}")
    print(f"Closure table -> {CLOSURE_PATH}")
    return str(CLOSURE_PATH)


if __name__ == "__main__":
    run()
