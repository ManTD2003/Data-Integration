from __future__ import annotations

import json
import re
from collections.abc import Iterator
from urllib.parse import quote

from .base import Fetcher

HOME = "https://vieclam24h.vn/"
SEARCH = "https://vieclam24h.vn/tim-kiem-viec-lam-nhanh"
NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)


def _job_list(html: str) -> dict:
    m = NEXT_DATA.search(html)
    if not m:
        return {}
    data = json.loads(m.group(1))
    return data["props"]["initialState"]["api"]["getJobList"]["data"]


class Vieclam24hWrapper:
    source = "vieclam24h"
    query_based = True

    def __init__(self, max_pages: int = 5):
        self.max_pages = max_pages
        self.fetcher = Fetcher(HOME)

    def search(self, query: str) -> Iterator[dict]:
        page = 1
        total_pages = 1
        while page <= min(self.max_pages, total_pages):
            url = f"{SEARCH}?q={quote(query)}&page={page}"
            payload = _job_list(self.fetcher.get(url))
            if not payload:
                break
            total_pages = payload.get("total_pages", 1)
            for item in payload.get("items", []):
                yield self._record(item, query)
            page += 1
            self.fetcher.sleep()

    def _record(self, item: dict, query: str) -> dict:
        item["_query"] = query
        item["_source"] = self.source
        return item

    def close(self) -> None:
        self.fetcher.close()
