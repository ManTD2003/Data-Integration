from src.integration.normalize import city_country, months_experience, role_family, salary, seniority


def test_role_family_maps_three_sources_to_one_vocabulary():
    """Chức danh tiếng Anh, từ khoá tiếng Việt và tiêu đề itviec phải ra cùng một nhóm."""
    assert role_family("Senior Data Engineer", "Data Engineer") == "Kỹ sư dữ liệu"
    assert role_family("Nhân Viên Lập Trình Cam", "lập trình") == "Kỹ sư phần mềm"
    assert role_family("Backend Developer (Java)", None) == "Kỹ sư phần mềm"


def test_role_family_falls_back_to_source_hint():
    assert role_family(None, "kế toán") == "Kế toán"
    assert role_family("", "thiết kế đồ họa") == "Thiết kế"


def test_role_family_unknown_title_returns_none():
    assert role_family("Chuyên Viên Pháp Chế", None) is None


def test_city_country_normalises_vietnamese_provinces():
    assert city_country("Thành phố Thủ Đức, Hồ Chí Minh", "vieclam24h") == ("TP Hồ Chí Minh", "Việt Nam")
    assert city_country("Ha Noi", "itviec") == ("Hà Nội", "Việt Nam")


def test_city_country_reads_province_code_when_address_has_no_province():
    """Địa chỉ vieclam24h bị nguồn cắt ngắn, phần lớn tin chỉ còn mã tỉnh để dựa vào."""
    city, _ = city_country("874 Bùi Hữu Nghĩa, Hoa A", "vieclam24h", province_id=120)
    assert city == "Đồng Nai"


def test_city_country_prefers_workplace_address_over_contact_address():
    city, _ = city_country(
        "Lô T2-1.1a, Khu Công Nghệ Cao, TP. Thủ Đức",
        "vieclam24h",
        province_id=73,
        address_hint="96 Hoàng Ngân, Yên Hòa, Hà Nội",
    )
    assert city == "TP Hồ Chí Minh"


def test_city_country_rejects_ward_and_street_names():
    """Tên phường hay số nhà không phải tỉnh thành, thà bỏ trống còn hơn lọt vào bộ lọc."""
    assert city_country("36/1/2B/5A Đường 4, khu phố 6, Phường Hiệp Bình Phước", "vieclam24h") == (
        None,
        "Việt Nam",
    )


def test_city_country_keeps_foreign_country_from_source_field():
    assert city_country("Watertown, CT", "data_jobs", "United States") == ("Watertown", "United States")


def test_city_country_takes_city_not_region_from_foreign_address():
    assert city_country("Bengaluru, Karnataka, India", "data_jobs", "India") == ("Bengaluru", "India")


def test_city_country_trusts_us_state_code_over_wrong_source_country():
    """Nguồn data_jobs gán 'Sudan' cho một loạt tin ở Mỹ; mã bang mới là căn cứ đúng."""
    assert city_country("Austin, TX", "data_jobs", "Sudan") == ("Austin", "United States")


def test_city_country_treats_country_only_string_as_country():
    assert city_country("India", "data_jobs", "India") == (None, "India")
    assert city_country("Singapore", "data_jobs", "Singapore") == ("Singapore", "Singapore")


def test_city_country_detects_remote():
    city, _ = city_country("Anywhere", "data_jobs", "United States")
    assert city == "Làm từ xa"


def test_seniority_reads_title_before_experience():
    assert seniority("Senior Backend Engineer", 12) == "Cao cấp"
    assert seniority("Thực Tập Sinh Kế Toán", None) == "Thực tập sinh"
    assert seniority("Backend Engineer", 36) == "Có kinh nghiệm"
    assert seniority("Backend Engineer", None) is None


def test_months_experience_parses_itviec_level():
    assert months_experience("37 months") == 37
    assert months_experience("senior") is None
    assert months_experience(None) is None


def test_salary_splits_vieclam24h_range_as_vnd():
    assert salary("15000000-20000000", "vieclam24h") == (15000000.0, 20000000.0, "VND", "month")


def test_salary_uses_single_value_for_data_jobs():
    assert salary("95000", "data_jobs") == (95000.0, 95000.0, "USD", "year")


def test_salary_reads_currency_from_the_string_not_the_source():
    low, high, currency, _ = salary("$1,000 - $2,000", "itviec")
    assert (low, high, currency) == (1000.0, 2000.0, "USD")


def test_salary_treats_million_scale_as_vnd_even_with_dollar_sign():
    """Tin ghi '$' nhưng con số cỡ chục triệu là lương VNĐ viết nhầm ký hiệu."""
    _, _, currency, _ = salary("$15,000,000", "itviec")
    assert currency == "VND"


def test_salary_missing_returns_all_none():
    assert salary(None, "itviec") == (None, None, None, None)
