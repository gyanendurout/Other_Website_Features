"""Minimal stdlib client for a self-hosted Firecrawl instance."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE_URL = os.environ.get("FIRECRAWL_URL", "http://localhost:3002")
TIMEOUT = int(os.environ.get("FIRECRAWL_TIMEOUT", "180"))


class FirecrawlError(RuntimeError):
    pass


def _post(path: str, payload: dict, timeout: int = TIMEOUT) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_up(timeout: int = 5) -> bool:
    """True if the Firecrawl API is reachable."""
    for path in ("/test", "/"):
        try:
            with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=timeout) as r:
                if r.status < 500:
                    return True
        except urllib.error.HTTPError as e:
            if e.code < 500:          # responding, just not that route
                return True
        except Exception:
            continue
    return False


def scrape(url: str, formats=("markdown",), only_main: bool = True,
           wait_ms: int = 0, timeout: int = TIMEOUT) -> dict:
    """Scrape one URL. Tries the v2 API, falls back to v1.

    Returns the inner `data` dict: {markdown, metadata: {title, statusCode, ...}}
    """
    payload = {"url": url, "formats": list(formats), "onlyMainContent": only_main}
    if wait_ms:
        payload["waitFor"] = wait_ms

    last_err = None
    for version in ("v2", "v1"):
        try:
            body = _post(f"/{version}/scrape", payload, timeout)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            last_err = f"{version} HTTP {e.code}: {detail}"
            continue
        except Exception as e:                      # connection refused, timeout
            last_err = f"{version}: {e}"
            continue

        if body.get("success") is False:
            last_err = f"{version}: {body.get('error') or body}"
            continue
        return body.get("data") or body

    raise FirecrawlError(f"scrape failed for {url} -> {last_err}")


def map_site(url: str, limit: int = 200, search: str | None = None,
             timeout: int = 90) -> list[str]:
    """List URLs discoverable on a site (fast, no full scrape)."""
    payload = {"url": url, "limit": limit}
    if search:
        payload["search"] = search

    last_err = None
    for version in ("v2", "v1"):
        try:
            body = _post(f"/{version}/map", payload, timeout)
        except Exception as e:
            last_err = f"{version}: {e}"
            continue
        links = body.get("links") or (body.get("data") or {}).get("links") or []
        # v2 may return dicts, v1 returns plain strings
        return [l["url"] if isinstance(l, dict) else l for l in links]
    raise FirecrawlError(f"map failed for {url} -> {last_err}")
