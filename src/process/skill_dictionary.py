"""Từ điển kỹ năng mầm: nền cho gazetteer/fuzzy matching ở extract_skills.py.

Nguồn: (1) khai thác skills_given có sẵn từ itviec/data_jobs (mỏ dữ liệu miễn phí,
đã được nguồn tự gắn nhãn); (2) bổ sung tay cho các ngành ngoài IT (vieclam24h đa
ngành: kế toán, marketing, xây dựng, bán hàng...) và kỹ năng mềm chung, vì hai
nguồn IT không phủ được nhóm này.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from src.common.paths import STAGING
from src.common.schema import strip_accents

DICTIONARY_PATH = STAGING / "skill_dictionary.json"

# Tag của nguồn trộn lẫn kỹ năng với tên vị trí tuyển dụng. Giữ lại tên vị trí thì
# gazetteer khớp "Senior Data Engineer" thành kỹ năng "Data Engineer" — sai loại
# thực thể, và làm bẩn cả bảng xếp hạng nhu cầu kỹ năng.
ROLE_TERMS = {
    "data engineer",
    "data scientist",
    "data analyst",
    "software engineer",
    "bridge engineer",
    "product owner",
    "tester",
    "qa qc",
    "system admin",
    "presale",
}

# Viết tắt thông dụng không xuất hiện trong tag của nguồn nên không mine được.
# Chỉ nhận các viết tắt không nhập nhằng: "js"/"ts"/"ml" bị loại vì chúng cũng là
# token thường gặp trong văn bản tiếng Việt, thêm vào sẽ sinh dương tính giả.
EXTRA_ALIASES: dict[str, list[str]] = {
    "Kubernetes": ["k8s"],
    "PostgreSql": ["postgres"],
    "Giao tiếp": [
        "communication skills",
        "strong communication skills",
        "excellent communication skills",
        "communicate effectively",
        "interpersonal skills",
    ],
    "Giải quyết vấn đề": ["problem-solving", "problem-solving skills"],
    "Chịu áp lực công việc": [
        "làm việc dưới áp lực",
        "khả năng chịu áp lực",
        "chịu áp lực cao",
        "work well under pressure",
    ],
    "Tinh thần trách nhiệm": [
        "có tinh thần trách nhiệm",
        "high sense of responsibility",
    ],
    "Tin học văn phòng": [
        "ứng dụng văn phòng",
        "office applications",
        "office software",
        "office văn phòng",
    ],
    "Risk Management": [
        "risk assessment",
        "technical risk assessment",
        "risk mitigation",
        "risk register",
        "risk control",
    ],
    "Data Analysis": [
        "data analytics",
        "analyze data",
        "analyse data",
        "phân tích dữ liệu",
    ],
    "Information Security": [
        "an ninh thông tin",
        "an toàn thông tin",
        "bảo mật thông tin",
        "attt",
    ],
    "UI-UX": [
        "ui/ux",
        "ui ux",
        "ux design",
        "user experience design",
        "user interface design",
    ],
    "Identity & Access Management": ["identity and access management", "iam"],
    "Web Application Firewall": ["waf"],
    "Automation Test": ["automated testing", "automation testing", "test automation"],
    "Technical Writing": ["technical documentation"],
    "Organizational Skills": ["work organization"],
}

# Kỹ năng mined từ skills_given thường là công cụ/công nghệ cụ thể (hard). Vài mục
# mang tính quản lý/con người thì cần gắn lại thành soft.
SOFT_OVERRIDES = {
    "leadership",
    "team management",
    "stakeholder management",
    "communication",
    "japanese it communication",
}

# (canonical_name, skill_type, [alias,...]) — alias dùng để đối sánh, không phân
# biệt hoa/thường và dấu.
SUPPLEMENT: list[tuple[str, str, list[str]]] = [
    ("Giao tiếp", "soft", ["giao tiếp", "kỹ năng giao tiếp", "communication skill"]),
    ("Làm việc nhóm", "soft", ["làm việc nhóm", "team work", "teamwork"]),
    ("Quản lý thời gian", "soft", ["quản lý thời gian", "time management"]),
    ("Giải quyết vấn đề", "soft", ["giải quyết vấn đề", "problem solving"]),
    ("Tư duy phản biện", "soft", ["tư duy phản biện", "critical thinking"]),
    ("Chịu áp lực công việc", "soft", ["chịu áp lực", "chịu được áp lực cao", "work under pressure"]),
    ("Đàm phán", "soft", ["đàm phán", "negotiation"]),
    ("Thuyết trình", "soft", ["thuyết trình", "presentation skill"]),
    ("Chăm chỉ", "soft", ["chăm chỉ", "chịu khó", "siêng năng"]),
    ("Trung thực", "soft", ["trung thực", "honest"]),
    ("Cẩn thận, tỉ mỉ", "soft", ["cẩn thận", "tỉ mỉ"]),
    ("Chủ động trong công việc", "soft", ["chủ động", "proactive"]),
    ("Tinh thần trách nhiệm", "soft", ["tinh thần trách nhiệm", "trách nhiệm trong công việc"]),
    ("Kỹ năng quản lý", "soft", ["kỹ năng quản lý", "quản lý nhân sự"]),
    ("Bán hàng", "hard", ["bán hàng", "kỹ năng bán hàng", "sales skill", "kinh doanh"]),
    ("Chăm sóc khách hàng", "hard", ["chăm sóc khách hàng", "customer service", "cskh"]),
    ("Telesale", "hard", ["telesale", "tư vấn qua điện thoại"]),
    ("Tuyển dụng", "hard", ["tuyển dụng", "recruitment"]),
    ("Tính lương, C&B", "hard", ["c&b", "tính lương", "compensation and benefits"]),
    ("Kế toán thuế", "hard", ["kế toán thuế", "kê khai thuế", "tax accounting"]),
    ("Kế toán công nợ", "hard", ["kế toán công nợ", "kế toán thanh toán"]),
    ("Phần mềm kế toán MISA", "hard", ["misa", "phần mềm kế toán misa"]),
    ("Tin học văn phòng", "hard", ["tin học văn phòng", "microsoft office", "ms office"]),
    ("Word", "hard", ["word", "microsoft word"]),
    ("Photoshop", "hard", ["photoshop"]),
    ("Adobe Illustrator", "hard", ["illustrator", "adobe illustrator"]),
    ("Adobe Premiere", "hard", ["premiere", "adobe premiere"]),
    ("CorelDRAW", "hard", ["corel", "coreldraw"]),
    ("AutoCAD", "hard", ["autocad"]),
    ("SEO", "hard", ["seo"]),
    ("Content Marketing", "hard", ["content marketing", "viết content"]),
    ("Digital Marketing", "hard", ["digital marketing"]),
    ("Social Media Marketing", "hard", ["social media", "mạng xã hội", "mxh"]),
    ("Quảng cáo Facebook", "hard", ["facebook ads", "quảng cáo facebook"]),
    ("Quảng cáo Google", "hard", ["google ads", "quảng cáo google"]),
    ("Quản lý dự án", "hard", ["quản lý dự án", "project management"]),
    ("Giám sát công trình", "hard", ["giám sát công trình", "giám sát thi công"]),
    ("Dự toán xây dựng", "hard", ["dự toán xây dựng", "bóc tách khối lượng"]),
    ("Đọc bản vẽ kỹ thuật", "hard", ["đọc bản vẽ", "bản vẽ kỹ thuật"]),
    ("Tiếng Anh", "hard", ["tiếng anh", "english"]),
    ("Tiếng Trung", "hard", ["tiếng trung", "chinese"]),
    ("Tiếng Nhật", "hard", ["tiếng nhật", "japanese"]),
    ("Tiếng Hàn", "hard", ["tiếng hàn", "korean"]),
    ("Amazon CloudWatch", "hard", ["amazon cloudwatch", "cloudwatch"]),
    ("Amazon EC2", "hard", ["amazon ec2", "aws ec2", "ec2"]),
    (
        "Infrastructure as Code",
        "hard",
        ["infrastructure as code", "infrastructure-as-code", "iac"],
    ),
    ("CircleCI", "hard", ["circleci", "circle ci"]),
    ("Root Cause Analysis", "hard", ["root cause analysis", "root-cause analysis", "rca"]),
    ("High Availability", "hard", ["high availability"]),
    ("Observability", "hard", ["observability"]),
    (
        "Backend Development",
        "hard",
        ["backend development", "back-end development", "phát triển backend"],
    ),
    (
        "Frontend Development",
        "hard",
        ["frontend development", "front-end development", "phát triển frontend"],
    ),
    ("Data Structures", "hard", ["data structures", "data structure"]),
    ("Algorithms", "hard", ["algorithms", "algorithm"]),
    ("Design Patterns", "hard", ["design patterns", "design pattern"]),
    ("System Design", "hard", ["system design"]),
    ("Distributed Systems", "hard", ["distributed systems", "distributed system"]),
    ("Hibernate", "hard", ["hibernate"]),
    ("Query Optimization", "hard", ["query optimization", "query optimisation"]),
    ("Database Performance Tuning", "hard", ["database performance tuning", "database tuning"]),
    ("Database Clustering", "hard", ["database clustering"]),
    ("Manual Testing", "hard", ["manual testing", "manual test"]),
    ("Performance Testing", "hard", ["performance testing", "performance test"]),
    ("Regression Testing", "hard", ["regression testing", "regression test"]),
    ("User Acceptance Testing", "hard", ["user acceptance testing", "uat"]),
    ("System Testing", "hard", ["system testing", "system test"]),
    ("Acceptance Criteria", "hard", ["acceptance criteria", "acceptance criterion"]),
    ("Intrusion Prevention System", "hard", ["intrusion prevention system", "ips"]),
    ("Data Loss Prevention", "hard", ["data loss prevention", "dlp"]),
    ("Privileged Access Management", "hard", ["privileged access management", "pam"]),
    ("Endpoint Security", "hard", ["endpoint security"]),
    ("Antivirus", "hard", ["antivirus", "anti-virus"]),
    ("NIST Cybersecurity Framework", "hard", ["nist cybersecurity framework", "nist csf"]),
    (
        "Security Operations Center",
        "hard",
        ["security operations center", "security operations centre"],
    ),
    ("Virtual Private Network", "hard", ["virtual private network", "vpn"]),
    ("TCP/IP", "hard", ["tcp/ip", "tcp ip"]),
    ("OSCP", "hard", ["oscp"]),
    ("CCNP", "hard", ["ccnp"]),
    ("CISA", "hard", ["cisa"]),
    ("CISSP", "hard", ["cissp"]),
    ("AI Agents", "hard", ["ai agents", "ai agent"]),
    ("Core Banking", "hard", ["core banking"]),
    ("Claude Code", "hard", ["claude code"]),
    ("Kiro", "hard", ["kiro"]),
    ("Market Research", "hard", ["market research", "nghiên cứu thị trường"]),
    (
        "Independent Working",
        "soft",
        ["independent working", "work independently", "làm việc độc lập"],
    ),
    (
        "Organizational Skills",
        "soft",
        [
            "organizational skills",
            "organisational skills",
            "tổ chức công việc",
            "sắp xếp công việc",
        ],
    ),
    (
        "Continuous Learning",
        "soft",
        ["continuous learning", "willingness to learn", "ham học hỏi"],
    ),
    ("Mentoring", "soft", ["mentoring", "mentor team members"]),
    ("Creative Thinking", "soft", ["creative thinking", "tư duy sáng tạo"]),
]

DEVELOPMENT_OOV_SUPPLEMENT: list[tuple[str, str, list[str]]] = [
    ("Platform Governance", "hard", ["platform governance"]),
    ("Quality Management", "hard", ["quality management"]),
    ("Refactoring", "hard", ["refactoring", "code refactoring"]),
    ("UML", "hard", ["uml", "unified modeling language"]),
    ("Information Architecture", "hard", ["information architecture"]),
    ("Interaction Design", "hard", ["interaction design"]),
    ("UX Research", "hard", ["ux research", "user experience research"]),
    ("Conversational UX", "hard", ["conversational ux"]),
    ("Product Thinking", "hard", ["product thinking"]),
    ("Product Analytics", "hard", ["product analytics"]),
    ("Product Discovery", "hard", ["product discovery"]),
    ("Rapid Prototyping", "hard", ["rapid prototyping"]),
    ("FigJam", "hard", ["figjam"]),
    ("Sales Automation", "hard", ["sales automation"]),
    ("SaaS", "hard", ["saas", "software as a service"]),
    ("FTTH", "hard", ["ftth", "fiber to the home"]),
    ("GIS", "hard", ["gis", "geographic information system"]),
    ("GPON", "hard", ["gpon"]),
    ("ODN", "hard", ["odn", "optical distribution network"]),
    ("OLT", "hard", ["olt", "optical line terminal"]),
    ("ONT", "hard", ["ont", "optical network terminal"]),
    ("XGS-PON", "hard", ["xgs-pon", "xgs pon"]),
    ("Digital Banking", "hard", ["digital banking"]),
    ("Digital Onboarding", "hard", ["digital onboarding"]),
    ("eKYC", "hard", ["ekyc", "electronic know your customer"]),
    ("Internet Banking", "hard", ["internet banking"]),
    ("Mobile Banking", "hard", ["mobile banking"]),
    ("Self-Service Banking", "hard", ["self-service banking", "self service banking"]),
    ("Autify", "hard", ["autify"]),
    ("ISTQB", "hard", ["istqb"]),
    ("MagicPod", "hard", ["magicpod", "magic pod"]),
    ("Mobile Application Testing", "hard", ["mobile application testing", "mobile app testing"]),
    ("Test Analysis", "hard", ["test analysis"]),
    ("Test Design", "hard", ["test design"]),
    ("Test Execution", "hard", ["test execution"]),
    ("Cucumber", "hard", ["cucumber"]),
    ("Android Espresso", "hard", ["android espresso", "espresso testing"]),
    ("Integration Testing", "hard", ["integration testing", "integration test"]),
    ("UIAutomator", "hard", ["uiautomator", "ui automator"]),
    ("XCUITest", "hard", ["xcuitest", "xcui test"]),
    ("Accessibility Testing", "hard", ["accessibility testing"]),
    ("Cypress", "hard", ["cypress"]),
    ("WCAG", "hard", ["wcag", "web content accessibility guidelines"]),
    ("Nuxt.js", "hard", ["nuxt.js", "nuxtjs", "nuxt"]),
    ("Swagger", "hard", ["swagger"]),
    ("OpenAPI", "hard", ["openapi", "open api"]),
    ("RESTful API", "hard", ["restful api", "rest api"]),
    ("API Integration", "hard", ["api integration"]),
    ("Cursor", "hard", ["cursor ai", "cursor ide", "cursor"]),
    ("ChatGPT", "hard", ["chatgpt", "chat gpt"]),
    ("OpenAI", "hard", ["openai"]),
    ("Azure OpenAI", "hard", ["azure openai"]),
    ("Anthropic", "hard", ["anthropic"]),
    ("n8n", "hard", ["n8n"]),
    ("Zapier", "hard", ["zapier"]),
    ("AI Automation", "hard", ["ai automation"]),
    ("Spatial AI", "hard", ["spatial ai"]),
    ("Workflow Orchestration", "hard", ["workflow orchestration"]),
    ("Data Pipelines", "hard", ["data pipelines", "data pipeline"]),
    ("FHIR", "hard", ["fhir", "fast healthcare interoperability resources"]),
    ("HL7", "hard", ["hl7"]),
    (
        "Hospital Information System (HIS)",
        "hard",
        ["hospital information system", "his system"],
    ),
    ("ICD-10", "hard", ["icd-10", "icd 10"]),
    ("Mastercam", "hard", ["mastercam"]),
    ("Camunda BPM", "hard", ["camunda bpm", "camunda"]),
    ("DMN", "hard", ["dmn", "decision model and notation"]),
    ("IBM ODM", "hard", ["ibm odm"]),
    ("Keycloak", "hard", ["keycloak"]),
    ("RabbitMQ", "hard", ["rabbitmq", "rabbit mq"]),
    ("Rancher", "hard", ["rancher"]),
    ("Spring Cloud", "hard", ["spring cloud"]),
    ("Spring Data", "hard", ["spring data"]),
    ("Spring Security", "hard", ["spring security"]),
    ("jOOQ", "hard", ["jooq"]),
    ("JPA", "hard", ["jpa", "java persistence api"]),
    ("Caching", "hard", ["caching", "cache management"]),
    ("Scripting", "hard", ["scripting", "script development"]),
    ("Code Review", "hard", ["code review", "code reviewing"]),
    ("Performance Optimization", "hard", ["performance optimization", "performance optimisation"]),
    ("Plugin Development", "hard", ["plugin development"]),
    ("Responsive Web Design", "hard", ["responsive web design"]),
    ("Spring MVC", "hard", ["spring mvc"]),
    ("Bootstrap", "hard", ["bootstrap"]),
    ("CodeIgniter", "hard", ["codeigniter", "code igniter"]),
    ("Tailwind CSS", "hard", ["tailwind css", "tailwindcss"]),
    ("Hybrid Cloud", "hard", ["hybrid cloud"]),
    ("Logging", "hard", ["logging", "log management"]),
    ("Capacity Planning", "hard", ["capacity planning"]),
    ("Artifactory", "hard", ["artifactory"]),
    ("Packer", "hard", ["hashicorp packer", "packer"]),
    ("Backstage", "hard", ["backstage"]),
    ("Grafana", "hard", ["grafana"]),
    ("Prometheus", "hard", ["prometheus"]),
    ("Postfix", "hard", ["postfix"]),
    ("SQL Injection", "hard", ["sql injection"]),
    ("API Protection", "hard", ["api protection"]),
    ("Network Access Control", "hard", ["network access control", "nac"]),
    ("Email Security Gateway", "hard", ["email security gateway"]),
    ("Vulnerability Management", "hard", ["vulnerability management"]),
    ("CIS Controls", "hard", ["cis controls"]),
    ("CCNA", "hard", ["ccna"]),
    ("CCSP", "hard", ["ccsp"]),
    ("CEH", "hard", ["ceh"]),
    ("CHFI", "hard", ["chfi"]),
    ("ECSA", "hard", ["ecsa"]),
    ("CISM", "hard", ["cism"]),
    ("CRISC", "hard", ["crisc"]),
    ("Affiliate Marketing", "hard", ["affiliate marketing"]),
    ("Google Trends", "hard", ["google trends"]),
    ("Semrush", "hard", ["semrush"]),
    ("Canva", "hard", ["canva"]),
    ("Game Economy Design", "hard", ["game economy design"]),
    ("Player Segmentation", "hard", ["player segmentation"]),
    ("Probability Modeling", "hard", ["probability modeling", "probability modelling"]),
    ("Core Banking Platform", "hard", ["core banking platform"]),
    ("Card Systems", "hard", ["card systems", "card system"]),
    ("Finacle", "hard", ["finacle"]),
    ("Mambu", "hard", ["mambu"]),
    ("T24", "hard", ["temenos t24", "t24"]),
    ("CBAP", "hard", ["cbap"]),
    ("PMI-ACP", "hard", ["pmi-acp", "pmi acp"]),
    ("PSPO", "hard", ["pspo"]),
    ("SAFe POPM", "hard", ["safe popm"]),
    ("Creo", "hard", ["creo"]),
    ("Weldments", "hard", ["weldments"]),
    ("Lean Manufacturing", "hard", ["lean manufacturing"]),
    ("Manufacturing Quality", "hard", ["manufacturing quality"]),
    ("Part Measurement", "hard", ["part measurement"]),
    ("Tool Engineering", "hard", ["tool engineering"]),
    ("Analytical Skills", "soft", ["analytical skills"]),
    ("Empathy", "soft", ["empathy"]),
    ("Self-Discipline", "soft", ["self-discipline", "self discipline"]),
    ("Team Building", "soft", ["team building"]),
]


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().strip()
    return re.sub(r"\s+", " ", text)


# NFKD không tách được "đ" và mọi ký hiệu đều bị bỏ, nên C#/C++/C cùng rơi về slug
# "c" rồi phải phân biệt bằng hậu tố số theo thứ tự chèn — nghĩa là cùng một skill_id
# có thể trỏ sang kỹ năng khác sau mỗi lần dựng lại từ điển. Phiên âm trước khi lọc.
SYMBOL_MAP = [
    ("c++", "c-plus-plus"),
    ("c#", "c-sharp"),
    ("f#", "f-sharp"),
    (".net", "-dotnet"),
    ("&", "-and-"),
    ("+", "-plus"),
    ("#", "-sharp"),
]


def _slugify(name: str) -> str:
    text = _fold(name)
    for symbol, replacement in SYMBOL_MAP:
        text = text.replace(symbol, replacement)
    slug = re.sub(r"[^a-z0-9]+", "-", strip_accents(text)).strip("-")
    return slug or "skill"


def _pick_display_form(variants: Counter) -> str:
    """Ưu tiên biến thể có chữ hoa (tên riêng/viết tắt chuẩn ngành) làm tên hiển thị."""
    proper_cased = {v: c for v, c in variants.items() if any(ch.isupper() for ch in v)}
    pool = proper_cased or variants
    return max(pool.items(), key=lambda kv: kv[1])[0]


class SkillDictionary:
    def __init__(self) -> None:
        self.skills: dict[str, dict] = {}
        self.alias_index: dict[str, str] = {}

    def _new_skill(self, skill_id: str, canonical_name: str, skill_type: str, is_category: bool) -> None:
        self.skills[skill_id] = {
            "skill_id": skill_id,
            "canonical_name": canonical_name,
            "skill_type": skill_type,
            "aliases": [],
            "parent_skill_id": None,
            "is_category": is_category,
        }

    def add(
        self, canonical_name: str, skill_type: str, aliases: list[str], is_category: bool = False
    ) -> str:
        all_aliases = {_fold(canonical_name), *[_fold(a) for a in aliases]}
        existing_id = next((self.alias_index[a] for a in all_aliases if a in self.alias_index), None)

        if existing_id is None:
            skill_id = _slugify(canonical_name)
            suffix = 2
            while skill_id in self.skills:
                skill_id = f"{_slugify(canonical_name)}-{suffix}"
                suffix += 1
            self._new_skill(skill_id, canonical_name, skill_type, is_category)
            existing_id = skill_id

        entry = self.skills[existing_id]
        for alias in all_aliases:
            self.alias_index[alias] = existing_id
            if alias not in entry["aliases"]:
                entry["aliases"].append(alias)
        return existing_id

    def for_extraction(self) -> SkillDictionary:
        """Bản từ điển bỏ các nút nhóm do bước phân cấp sinh ra.

        Nếu không lọc, chạy lại bước trích chọn sau bước phân cấp sẽ khớp thêm chính
        các nhãn nhóm ("ngôn ngữ lập trình", "cơ sở dữ liệu"...) mà bước trích chọn
        chạy trước đó không hề thấy — kết quả phụ thuộc thứ tự chạy.
        """
        view = SkillDictionary()
        for skill_id, entry in self.skills.items():
            if entry.get("is_category"):
                continue
            view.skills[skill_id] = entry
            for alias in entry["aliases"]:
                view.alias_index[alias] = skill_id
        return view

    def lookup(self, alias: str) -> dict | None:
        skill_id = self.alias_index.get(_fold(alias))
        return self.skills.get(skill_id) if skill_id else None

    def to_json(self) -> list[dict]:
        return list(self.skills.values())


def _mine_from_records(records: list[dict]) -> Counter:
    """Đếm tần suất từng biến thể chữ trong skills_given (itviec + data_jobs)."""
    variants: Counter = Counter()
    for rec in records:
        for raw_skill in rec.get("extra", {}).get("skills_given") or []:
            name = raw_skill.strip()
            if name:
                variants[name] += 1
    return variants


def build_dictionary(records: list[dict]) -> SkillDictionary:
    mined = _mine_from_records(records)
    grouped: dict[str, Counter] = {}
    for name, count in mined.items():
        folded = _fold(name)
        if folded in ROLE_TERMS:
            continue
        grouped.setdefault(folded, Counter())[name] += count

    skill_dict = SkillDictionary()
    for folded, variants in grouped.items():
        skill_type = "soft" if folded in SOFT_OVERRIDES else "hard"
        display_name = _pick_display_form(variants)
        skill_dict.add(display_name, skill_type, list(variants))

    for canonical_name, skill_type, aliases in [*SUPPLEMENT, *DEVELOPMENT_OOV_SUPPLEMENT]:
        skill_dict.add(canonical_name, skill_type, aliases)

    for canonical_name, aliases in EXTRA_ALIASES.items():
        entry = skill_dict.lookup(canonical_name)
        if entry is not None:
            skill_dict.add(entry["canonical_name"], entry["skill_type"], aliases)

    return skill_dict


def load_or_build(records: list[dict], force_rebuild: bool = False) -> SkillDictionary:
    if not force_rebuild and DICTIONARY_PATH.exists():
        skill_dict = SkillDictionary()
        for entry in json.loads(DICTIONARY_PATH.read_text(encoding="utf-8")):
            entry.setdefault("is_category", False)
            skill_dict.skills[entry["skill_id"]] = entry
            for alias in entry["aliases"]:
                skill_dict.alias_index[alias] = entry["skill_id"]
        return skill_dict

    skill_dict = build_dictionary(records)
    DICTIONARY_PATH.write_text(
        json.dumps(skill_dict.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return skill_dict


def run() -> str:
    records_path = STAGING / "records_deduped.jsonl"
    records = [json.loads(line) for line in open(records_path, encoding="utf-8")]
    skill_dict = load_or_build(records, force_rebuild=True)

    hard = sum(1 for s in skill_dict.skills.values() if s["skill_type"] == "hard")
    soft = sum(1 for s in skill_dict.skills.values() if s["skill_type"] == "soft")
    print(f"Skills: {len(skill_dict.skills)} (hard={hard}, soft={soft}) | aliases: {len(skill_dict.alias_index)}")

    slugs = Counter(_slugify(s["canonical_name"]) for s in skill_dict.skills.values())
    collided = {slug: n for slug, n in slugs.items() if n > 1}
    if collided:
        print("Slug trùng, skill_id phải thêm hậu tố số:", collided)

    print(f"Từ điển -> {DICTIONARY_PATH}")
    return str(DICTIONARY_PATH)


if __name__ == "__main__":
    run()
