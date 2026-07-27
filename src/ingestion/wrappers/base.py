from __future__ import annotations

import random
import time

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

DESKTOP_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class Blocked(Exception):
    pass


class Fetcher:
    """HTTP client giữ cookie phiên; hâm nóng trang chủ trước để qua WAF."""

    def __init__(self, home: str, min_delay: float = 1.0, max_delay: float = 2.5):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.client = httpx.Client(
            headers={
                "User-Agent": DESKTOP_UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "vi,en;q=0.9",
            },
            timeout=25.0,
            follow_redirects=True,
        )
        self.client.get(home)

    @retry(
        retry=retry_if_exception_type((Blocked, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=15),
        reraise=True,
    )
    def get(self, url: str) -> str:
        resp = self.client.get(url)
        if resp.status_code in (403, 429):
            raise Blocked(f"{resp.status_code} {url}")
        resp.raise_for_status()
        return resp.text

    def sleep(self) -> None:
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    def close(self) -> None:
        self.client.close()
