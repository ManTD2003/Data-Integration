"""Chuẩn hoá các chiều mô tả tin tuyển dụng về một từ vựng chung.

Ba nguồn mô tả cùng một khái niệm theo ba cách không so được với nhau: nhóm nghề của
data_jobs là chức danh tiếng Anh, của vieclam24h là từ khoá đã dùng khi cào, còn
itviec không có; địa điểm thì trộn tỉnh thành Việt Nam với bang và quốc gia; cấp bậc
thì một nguồn ghi mã số, một nguồn ghi số tháng kinh nghiệm. Đưa chúng về từ vựng
chung ở đây, thay vì để nguyên giá trị nguồn trong kho, mới lọc và tổng hợp được.
"""

from __future__ import annotations

import re

from src.common.schema import strip_accents

# --- Nhóm nghề ---------------------------------------------------------------

ROLE_FAMILIES: list[tuple[str, tuple[str, ...]]] = [
    ("Kỹ sư dữ liệu", ("data engineer", "ky su du lieu", "etl developer")),
    ("Khoa học dữ liệu", ("data scientist", "khoa hoc du lieu", "machine learning", "ai engineer")),
    ("Phân tích dữ liệu", ("data analyst", "phan tich du lieu", "bi analyst", "business intelligence")),
    ("Phân tích nghiệp vụ", ("business analyst", "phan tich nghiep vu", "ba ")),
    ("Kiểm thử", ("tester", "kiem thu", "qa qc", " qa ", "quality assurance", "sdet")),
    ("DevOps & hạ tầng", ("devops", "sre", "cloud engineer", "system admin", "ha tang", "infrastructure")),
    ("An ninh mạng", ("security", "an ninh mang", "bao mat")),
    ("Kỹ sư phần mềm", (
        "developer", "engineer", "lap trinh", "ky su phan mem", "programmer",
        "backend", "frontend", "fullstack", "software",
    )),
    ("Thiết kế", ("designer", "thiet ke", "ui-ux", "ui/ux", "do hoa")),
    ("Quản lý dự án", ("project manager", "quan ly du an", "scrum master", "product owner", "product manager")),
    ("Kế toán", ("ke toan", "accountant", "accounting", "kiem toan")),
    ("Nhân sự", ("nhan su", "human resource", " hr ", "tuyen dung", "recruiter")),
    ("Marketing", ("marketing", "seo", "content", "truyen thong")),
    ("Bán hàng & chăm sóc khách hàng", (
        "ban hang", "sales", "kinh doanh", "cham soc khach hang", "customer service", "telesale",
    )),
    ("Xây dựng", ("xay dung", "cong trinh", "kien truc su", "civil")),
]


def role_family(title: str | None, source_hint: str | None = None) -> str | None:
    """Suy nhóm nghề từ tiêu đề, lấy giá trị nguồn làm căn cứ dự phòng.

    Ưu tiên tiêu đề vì mọi nguồn đều có, còn `source_hint` (chức danh rút gọn của
    data_jobs, từ khoá cào của vieclam24h) chỉ có ở hai nguồn và không cùng từ vựng.
    """
    for text in (title, source_hint):
        if not text:
            continue
        padded = f" {strip_accents(text)} "
        for family, keywords in ROLE_FAMILIES:
            if any(keyword in padded for keyword in keywords):
                return family
    return None


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

REMOTE_TOKENS = ("anywhere", "remote", "work from home")


def city_country(location_raw: str | None, source: str, hint_country: str | None = None) -> tuple[str | None, str | None]:
    """Tách địa điểm thô thành (thành phố, quốc gia).

    Lấy đoạn cuối sau dấu phẩy là cách rẻ nhưng cho ra 'CA', 'UK', 'France' lẫn với
    'Hà Nội' trong cùng một cột. Ở đây tỉnh thành Việt Nam được đưa về tên chuẩn, còn
    tin nước ngoài lấy quốc gia từ chính trường quốc gia của nguồn.
    """
    if not location_raw:
        return None, ("Việt Nam" if source in ("vieclam24h", "itviec") else hint_country)

    folded = strip_accents(location_raw)
    if any(token in folded for token in REMOTE_TOKENS):
        return "Làm từ xa", hint_country or ("Việt Nam" if source != "data_jobs" else None)

    for city, keywords in VN_CITIES:
        if any(keyword in folded for keyword in keywords):
            return city, "Việt Nam"

    if source == "data_jobs":
        head = location_raw.split(",")[0].strip()
        return (head or None), hint_country

    return location_raw.split(",")[-1].strip() or None, "Việt Nam"


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
