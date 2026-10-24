import time
from typing import Any

import httpx2

USER_AGENT = "linuxserver-hub (+https://github.com/linuxserver-playground/hub)"
BACKOFF = 1.5
"""Seconds before the first retry; doubled each time."""
MAX_WAIT = 60
"""The longest a retry waits, even when the server's Retry-After asks for more."""


def client() -> httpx2.Client:
    return httpx2.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def request(http: httpx2.Client, method: str, url: str, *, retries: int = 3, **kwargs: Any) -> httpx2.Response:
    """
    A successful response, retrying network errors, 429 and 5xx with exponential backoff (or the server's
    Retry-After, up to MAX_WAIT). Raises httpx2.HTTPStatusError on any other error.
    """
    for attempt in range(retries + 1):
        wait = BACKOFF * 2**attempt
        try:
            res = http.request(method, url, **kwargs)
        except httpx2.TransportError:
            if attempt == retries:
                raise
        else:
            if res.is_success:
                return res
            if attempt == retries or (res.status_code != 429 and res.status_code < 500):
                res.raise_for_status()
            retry_after = res.headers.get("retry-after", "")
            if retry_after.isdigit():
                wait = float(retry_after)
        time.sleep(min(wait, MAX_WAIT))
    raise AssertionError("unreachable")


def request_json(http: httpx2.Client, method: str, url: str, **kwargs: Any) -> Any:
    return request(http, method, url, **kwargs).json()
