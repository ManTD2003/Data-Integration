"""Chuẩn hoá địa điểm, cấp bậc và lương của tin tuyển dụng.

Địa điểm trộn tỉnh thành Việt Nam với bang và quốc gia; cấp bậc có nguồn ghi mã số,
nguồn khác ghi số tháng kinh nghiệm. Các quy tắc dưới đây đưa những trường đó về
dạng có thể lọc và tổng hợp chung.
"""

from __future__ import annotations

import re

from src.common.schema import strip_accents

# --- Địa điểm ----------------------------------------------------------------

VN_CITIES: list[tuple[str, tuple[str, ...]]] = [
    ("Hà Nội", ("ha noi", "hanoi")),
    ("TP Hồ Chí Minh", ("ho chi minh", "hcm", "sai gon", "saigon", "thu duc")),
    ("Đà Nẵng", ("da nang", "danang")),
    ("Hải Phòng", ("hai phong",)),
    ("Cần Thơ", ("can tho",)),
    ("Bình Dương", ("binh duong",)),
    ("Đồng Nai", ("dong nai", "bien hoa")),
    ("Bắc Ninh", ("bac ninh",)),
    ("Bắc Giang", ("bac giang",)),
    ("Hưng Yên", ("hung yen",)),
    ("Hải Dương", ("hai duong",)),
    ("Quảng Ninh", ("quang ninh", "ha long")),
    ("Vĩnh Phúc", ("vinh phuc",)),
    ("Thái Nguyên", ("thai nguyen",)),
    ("Thanh Hoá", ("thanh hoa",)),
    ("Nghệ An", ("nghe an",)),
    ("Thừa Thiên Huế", ("thua thien", "hue")),
    ("Khánh Hoà", ("khanh hoa", "nha trang")),
    ("Bà Rịa - Vũng Tàu", ("ba ria", "vung tau")),
    ("Long An", ("long an",)),
    ("Tiền Giang", ("tien giang", "my tho")),
    ("Lâm Đồng", ("lam dong", "da lat")),
    ("Bình Định", ("binh dinh", "quy nhon")),
]

REMOTE_TOKENS = ("anywhere", "remote", "work from home", "lam tu xa")

# vieclam24h gắn mã tỉnh cho từng tin (`places[].province_id`) nhưng không phát hành
# bảng nghĩa. Bảng dưới suy từ chính dữ liệu đã cào: với mỗi mã, đọc tên tỉnh trong
# địa chỉ của các tin mang mã đó rồi lấy phương án chiếm đa số, chỉ giữ mã có từ 5
# phiếu và tỉ lệ áp đảo từ 70% trở lên. Ngưỡng cần cao vì địa chỉ liên hệ là trụ sở
# doanh nghiệp, không phải lúc nào cũng trùng nơi làm việc: mã 119 chỉ đạt 57% do
# nhiều công ty đặt trụ sở ở TP HCM nhưng tuyển cho nhà máy Bình Dương. Mã ngoài
# bảng thì để địa chỉ tự quyết.
VN_PROVINCE_IDS = {
    73: "Hà Nội",
    84: "Thái Nguyên",
    90: "Bắc Ninh",
    104: "Đà Nẵng",
    120: "Đồng Nai",
    122: "TP Hồ Chí Minh",
    131: "Cần Thơ",
}

# Quốc gia chỉ gồm một thành phố: chuỗi địa điểm trùng tên nước vẫn là tên thành phố.
CITY_STATES = frozenset({"Singapore", "Hong Kong", "Macau", "Luxembourg", "Monaco"})

US_STATES = frozenset(
    "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
    "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
)


def vn_city(text: str | None) -> str | None:
    """Tên tỉnh thành đọc được trong một chuỗi địa chỉ tiếng Việt."""
    folded = strip_accents(text)
    for city, keywords in VN_CITIES:
        if any(keyword in folded for keyword in keywords):
            return city
    return None


def _is_remote(*texts: str | None) -> bool:
    return any(token in strip_accents(text) for text in texts if text for token in REMOTE_TOKENS)


def city_country(
    location_raw: str | None,
    source: str,
    hint_country: str | None = None,
    *,
    province_id: int | None = None,
    address_hint: str | None = None,
) -> tuple[str | None, str | None]:
    """Tách địa điểm thô thành (thành phố, quốc gia).

    `city` chỉ nhận tên cấp tỉnh thành, không bao giờ nhận chuỗi tự do cắt ra từ địa
    chỉ. Cách cũ lấy đoạn cuối sau dấu phẩy làm thành phố, nhưng địa điểm vieclam24h
    là địa chỉ số nhà nên cột này đầy tên phường ("Phường 14", "Phường Hiệp Bình
    Phước") lẫn tên đường, còn tin nước ngoài thì ra mã bang 'CA', 'TX' — cả hai đều
    không dùng làm bộ lọc được. Không suy ra được tỉnh thành thì trả None, tin đó
    không xuất hiện trong bộ lọc địa điểm nhưng vẫn giữ nguyên `location_raw`.
    """
    if source == "data_jobs":
        return _foreign_location(location_raw, hint_country)
    return _vietnam_location(location_raw, province_id, address_hint)


def _vietnam_location(
    location_raw: str | None, province_id: int | None, address_hint: str | None
) -> tuple[str | None, str | None]:
    """Thứ tự tra: địa chỉ nơi làm việc, mã tỉnh của tin, rồi địa chỉ liên hệ.

    Địa chỉ nơi làm việc mà nói rõ tỉnh thì đó là căn cứ sát nhất, nhưng vieclam24h
    cắt ngắn trường này ("874 Bùi Hữu Nghĩa, Hoa A") nên chỉ 21% số tin đọc được tỉnh
    từ đó; mã tỉnh mới là trường phủ kín. Địa chỉ liên hệ xếp sau cùng vì là trụ sở
    doanh nghiệp chứ không phải nơi làm việc.
    """
    if _is_remote(location_raw, address_hint):
        return "Làm từ xa", "Việt Nam"
    city = vn_city(location_raw) or VN_PROVINCE_IDS.get(province_id) or vn_city(address_hint)
    return city, "Việt Nam"


def _foreign_location(location_raw: str | None, hint_country: str | None) -> tuple[str | None, str | None]:
    """Địa điểm data_jobs: 'Watertown, CT', 'Paris, France', 'India', 'Anywhere'.

    Không tin `job_country` khi địa điểm tự nói rõ hơn: 88 tin ở Mỹ ('Austin, TX',
    'Washington, DC') bị nguồn gán quốc gia 'Sudan', và không có cách nào phát hiện
    nếu chỉ đọc mỗi trường quốc gia.
    """
    if not location_raw:
        return None, hint_country
    if _is_remote(location_raw):
        return "Làm từ xa", None

    head, comma, tail = location_raw.rpartition(",")
    if comma:
        # Đoạn đầu mới là thành phố: "Bengaluru, Karnataka, India" phải ra Bengaluru,
        # giữ nguyên phần trước dấu phẩy cuối thì thành phố tách làm hai mục.
        city, tail = head.split(",")[0].strip(), tail.strip()
        if tail in US_STATES:
            return city or None, "United States"
        return (city or None), (hint_country or tail or None)

    # "Dubai - United Arab Emirates"
    head, dash, tail = location_raw.partition(" - ")
    if dash:
        return head.strip() or None, (hint_country or tail.strip() or None)

    if location_raw in CITY_STATES:
        return location_raw, hint_country or location_raw
    # Còn lại là chuỗi chỉ có tên nước ("United States", "India"), không phải thành phố.
    return None, location_raw


# --- Cấp bậc -----------------------------------------------------------------

SENIORITY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Thực tập sinh", ("intern", "thuc tap", "fresher", "moi tot nghiep")),
    ("Quản lý", ("manager", "truong phong", "giam doc", "director", "head of", "truong bo phan")),
    ("Trưởng nhóm", ("team lead", "leader", "truong nhom", "tech lead", "principal")),
    ("Cao cấp", ("senior", "sr.", "chuyen gia", "expert")),
    ("Mới vào nghề", ("junior", "jr.")),
]

MONTHS_RE = re.compile(r"(\d+)\s*months?")


def seniority(title: str | None, months_experience: int | None = None) -> str | None:
    """Cấp bậc suy từ tiêu đề, dự phòng bằng số tháng kinh nghiệm.

    Không đọc `level_requirement` của vieclam24h vì nguồn chỉ trả về mã số (1..6) mà
    không kèm bảng nghĩa, đoán bảng nghĩa thì không kiểm chứng được.
    """
    padded = f" {strip_accents(title)} " if title else ""
    for level, keywords in SENIORITY_RULES:
        if any(keyword in padded for keyword in keywords):
            return level
    if months_experience is None:
        return None
    if months_experience >= 60:
        return "Cao cấp"
    if months_experience >= 24:
        return "Có kinh nghiệm"
    return "Mới vào nghề"


def months_experience(level_raw: str | None) -> int | None:
    if not level_raw:
        return None
    match = MONTHS_RE.match(level_raw)
    return int(match.group(1)) if match else None


# --- Lương -------------------------------------------------------------------

SALARY_DEFAULT = {
    "vieclam24h": ("VND", "month"),
    "itviec": ("USD", "month"),
    "data_jobs": ("USD", "year"),
}

VND_TOKENS = ("vnd", "vnđ", "đ", "trieu", "triệu")
USD_TOKENS = ("usd", "$")


def salary(raw: str | None, source: str) -> tuple[float | None, float | None, str | None, str | None]:
    """Tách khoảng lương và suy đơn vị từ chính chuỗi gốc.

    Đơn vị mặc định theo nguồn chỉ đúng cho trường hợp phổ biến: itviec đăng lương USD
    nhưng thỉnh thoảng ghi VNĐ, nên chuỗi nào tự nói đơn vị thì tin chuỗi đó.
    """
    if not raw:
        return None, None, None, None

    currency, period = SALARY_DEFAULT.get(source, (None, None))
    folded = strip_accents(raw)
    if any(token in folded for token in USD_TOKENS) or "$" in raw:
        currency = "USD"
    elif any(token in raw.lower() for token in VND_TOKENS):
        currency = "VND"

    numbers = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    if not numbers:
        return None, None, currency, period

    low, high = min(numbers), max(numbers)
    # Chuỗi nói USD nhưng con số cỡ triệu thì đó là VNĐ viết kèm ký hiệu, không quy đổi.
    if currency == "USD" and low >= 1_000_000:
        currency = "VND"
    return low, high, currency, period
