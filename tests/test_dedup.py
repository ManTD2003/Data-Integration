from src.integration.dedup import assign_groups, blocking_key, company_key, is_duplicate


def _rec(source, source_id, title, company, **extra):
    return {"source": source, "source_id": source_id, "title": title, "company": company, **extra}


def test_company_key_drops_legal_form_prefix():
    """12 ký tự đầu của tên công ty Việt Nam là loại hình pháp lý, không phân biệt được
    doanh nghiệp nào với doanh nghiệp nào."""
    assert company_key("Công ty TNHH ABC Việt Nam").startswith("abc")
    assert company_key("CÔNG TY CỔ PHẦN ABC Việt Nam").startswith("abc")
    assert company_key("Công ty TNHH MTV Thương mại XYZ").startswith("xyz")


def test_blocking_key_separates_two_companies_with_same_legal_form():
    a = _rec("vieclam24h", "1", "Nhân viên kinh doanh", "Công ty TNHH Alpha")
    b = _rec("vieclam24h", "2", "Nhân viên kinh doanh", "Công ty TNHH Beta")
    assert blocking_key(a) != blocking_key(b)


def test_blocking_key_falls_back_to_title():
    rec = _rec("vieclam24h", "1", "Kế toán tổng hợp", None)
    assert blocking_key(rec) == "ke toan tong"


def test_duplicate_detected_across_sources():
    a = _rec("vieclam24h", "1", "Senior Backend Engineer", "Công ty TNHH ABC")
    b = _rec("itviec", "2", "Senior Backend Engineer", "ABC")
    assert is_duplicate(a, b)


def test_different_positions_at_same_company_are_not_duplicates():
    a = _rec("itviec", "1", "Senior Backend Engineer", "ABC")
    b = _rec("itviec", "2", "Senior Frontend Engineer", "ABC")
    assert not is_duplicate(a, b)


def test_assign_groups_keeps_the_record_that_carries_source_labels():
    """Gộp liên nguồn mà giữ nhầm bản ghi không có nhãn thì mất luôn kỹ năng của tin."""
    plain = _rec("vieclam24h", "1", "Data Engineer", "ABC", extra={}, requirements_raw="mô tả ngắn")
    labelled = _rec("itviec", "2", "Data Engineer", "ABC", extra={"skills_given": ["Python"]})
    records = [plain, labelled]

    assign_groups(records)

    assert plain["dup_group_id"] == labelled["dup_group_id"]
    assert labelled["is_canonical"]
    assert not plain["is_canonical"]


def test_assign_groups_marks_every_group_with_exactly_one_canonical():
    records = [
        _rec("itviec", "1", "Backend Engineer", "ABC"),
        _rec("itviec", "2", "Backend Engineer", "ABC"),
        _rec("itviec", "3", "Kế toán trưởng", "XYZ"),
    ]
    assign_groups(records)

    groups = {}
    for rec in records:
        groups.setdefault(rec["dup_group_id"], []).append(rec)
    assert len(groups) == 2
    assert all(sum(r["is_canonical"] for r in group) == 1 for group in groups.values())
