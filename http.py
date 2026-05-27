"""Direct-HTTP helper with TLS impersonation, optional Chrome cookies."""
from __future__ import annotations

from typing import Iterable

from curl_cffi import requests as creq

from .browser import ChromeProfile


def fetch_json(
    url: str,
    *,
    profile: ChromeProfile | None = None,
    domain: str | None = None,
    method: str = "GET",
    json_body: dict | None = None,
    headers: dict | None = None,
    skip_cookies: Iterable[str] = (),
    impersonate: str = "chrome131",
    timeout: int = 30,
):
    """Fetch a JSON endpoint, optionally with the user's logged-in cookies.

    Bot defenses that bind cookies to the original browser fingerprint
    (Imperva `reese84`, PerimeterX `_px*`, Cloudflare `cf_clearance`)
    will reject replay → use BrowserSession in those cases.
    """
    cookies = {}
    if profile and domain:
        skip = tuple(skip_cookies)
        for c in profile.cookies_for(domain):
            if any(c.name == s or c.name.startswith(s) for s in skip):
                continue
            cookies[c.name] = c.value
    hdrs = {
        "Accept": "application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        hdrs.update(headers)
    s = creq.Session(impersonate=impersonate)
    if method == "GET":
        r = s.get(url, cookies=cookies, headers=hdrs, timeout=timeout)
    else:
        r = s.request(method, url, cookies=cookies, headers=hdrs,
                      json=json_body, timeout=timeout)
    r.raise_for_status()
    return r.json()
