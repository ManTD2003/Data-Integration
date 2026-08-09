from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator

from selectolax.parser import HTMLParser

from .base import Fetcher

HOME = "https://itviec.com/"
LISTING = "https://itviec.com/it-jobs"
LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return _clean(HTMLParser(value).text(separator=" ")) or None


def _job_posting(html: str) -> dict | None:
    for block in LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if data.get("@type") == "JobPosting":
            return data
    return None


def _location(posting: dict) -> str | None:
    places = posting.get("jobLocation") or []
    if not places or not isinstance(places[0], dict):
        return None
    addr = places[0].get("address")
    if not isinstance(addr, dict):
        return None
    parts = [addr.get("addressLocality"), addr.get("addressRegion")]
    return ", ".join(p for p in parts if p) or None


def _salary(posting: dict) -> str | None:
    base = posting.get("baseSalary")
    value = base.get("value") if isinstance(base, dict) else None
    if not isinstance(value, dict):
        return None
    amount = value.get("value")
    if amount is None or not str(amount).replace(".", "").isdigit():
        return None
    return f"{amount} {base.get('currency', '')}/{value.get('unitText', '')}".strip()


def _months_experience(posting: dict) -> int | None:
    exp = posting.get("experienceRequirements")
    return exp.get("monthsOfExperience") if isinstance(exp, dict) else None


def _section(full_text: str, start: str, ends: list[str]) -> str | None:
    i = full_text.find(start)
    if i < 0:
        return None
    i += len(start)
    cut = len(full_text)
    for end in ends:
        j = full_text.find(end, i)
        if 0 <= j < cut:
            cut = j
    section = full_text[i:cut].strip()
    return section or None


class ItviecWrapper:
    source = "itviec"
    query_based = False

    def __init__(self, max_pages: int = 5, fetch_detail: bool = True):
        self.max_pages = max_pages
        self.fetch_detail = fetch_detail
        self.fetcher = Fetcher(HOME, min_delay=0.4, max_delay=0.9)

    def search(self, query: str | None = None) -> Iterator[dict]:
        for page in range(1, self.max_pages + 1):
            url = f"{LISTING}?page={page}"
            if query:
                url += f"&query={query}"
            cards = HTMLParser(self.fetcher.get(url)).css("div.job-card")
            if not cards:
                break
            for card in cards:
                rec = self._card(card)
                if rec:
                    if self.fetch_detail:
                        try:
                            self._enrich(rec)
                        except Exception as exc:
                            print(
                                f"itviec: không lấy được chi tiết {rec.get('slug')}: "
                                f"{type(exc).__name__} {exc}",
                                file=sys.stderr,
                            )
                            self.fetcher.sleep()
                    yield rec
            self.fetcher.sleep()

    def _card(self, card) -> dict | None:
        link = card.css_first("h3 a")
        if not link:
            return None
        company = None
        for a in card.css("a[href*='/companies/']"):
            if a.text(strip=True):
                company = a.text(strip=True)
                break
        if not company:
            img = card.css_first("img")
            if img:
                company = (img.attributes.get("alt") or "").replace(" Small Logo", "").strip() or None
        loc = card.css_first("div.text-dark-grey")
        skills = [x.text(strip=True) for x in card.css("a.itag") if x.text(strip=True)]
        attrs = card.attributes
        return {
            "_source": self.source,
            "job_key": attrs.get("data-job-key"),
            "slug": attrs.get("data-search--job-selection-job-slug-value"),
            "title": link.text(strip=True),
            "url": (link.attributes.get("href") or "").split("?")[0],
            "company": company,
            "location": _clean(loc.text()) if loc else None,
            "skills": skills,
        }

    def _enrich(self, rec: dict) -> None:
        slug = rec.get("slug")
        if not slug:
            return
        html = self.fetcher.get(f"{LISTING}/{slug}")
        full = _clean(HTMLParser(html).text(separator=" "))
        rec["description"] = _section(full, "Job description", ["Your skills and experience"])
        rec["requirements"] = _section(
            full,
            "Your skills and experience",
            ["Why you'll love working here", "Why you’ll love working here"],
        )
        posting = _job_posting(html)
        if posting:
            rec["date_posted"] = posting.get("datePosted")
            rec["valid_through"] = posting.get("validThrough")
            rec["employment_type"] = posting.get("employmentType")
            rec["industry"] = posting.get("industry")
            if posting.get("skills"):
                rec["skills_ld"] = [s.strip() for s in posting["skills"].split(",") if s.strip()]
            rec["months_experience"] = _months_experience(posting)
            rec["location"] = _location(posting) or rec.get("location")
            rec["salary_raw"] = _salary(posting)
            if not rec.get("description"):
                rec["description"] = _strip_html(posting.get("description"))
        self.fetcher.sleep()

    def close(self) -> None:
        self.fetcher.close()
