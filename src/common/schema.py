from __future__ import annotations

import hashlib
import unicodedata
from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class JobRecord(BaseModel):
    """Mediated schema (GAV target): mọi nguồn được ánh xạ về cấu trúc này."""

    source: str
    source_id: str
    url: str | None = None
    title: str
    company: str | None = None
    location: str | None = None
    salary_raw: str | None = None
    level: str | None = None
    job_type: str | None = None
    description: str | None = None
    requirements_raw: str | None = None
    posted_date: date | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def record_id(self) -> str:
        return f"{self.source}:{self.source_id}"

    def dedup_key(self) -> str:
        base = f"{norm_text(self.title)}|{norm_text(self.company)}"
        return hashlib.sha1(base.encode("utf-8")).hexdigest()


def norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.lower().split())


def strip_accents(value: str | None) -> str:
    """Bỏ dấu tiếng Việt, giữ nguyên ký hiệu ASCII (C++, C#, .NET).

    NFKD không tách được dấu của "đ" nên phải thay trước khi lọc ASCII.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFC", value).lower().replace("đ", "d")
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(folded.split())
