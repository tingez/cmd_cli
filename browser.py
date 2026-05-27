"""Shared Chrome-cookie + Playwright utilities used by authenticated scrapers.

Two main building blocks:

* `ChromeProfile` — resolves a profile display name to its on-disk folder
  ("Profile 1") and reads cookies for a domain. Sources declare which cookies
  to skip (bot-defense tokens that don't transfer).

* `BrowserSession` — context manager that launches a fresh Playwright
  Chromium, injects the cookies, exposes `page` for navigation and
  `request` for direct API calls.
"""
from __future__ import annotations

import contextlib
import dataclasses
import json
import pathlib
import sys
from typing import Iterable, Iterator

import browser_cookie3

CHROME_DIR = pathlib.Path.home() / "Library/Application Support/Google/Chrome"

DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclasses.dataclass
class ChromeProfile:
    """Resolves a profile name → folder path. Reads cookies for any domain."""

    folder: str          # e.g. "Default", "Profile 1"
    display_name: str    # e.g. "Person 1"

    @classmethod
    def list(cls) -> list["ChromeProfile"]:
        local_state = CHROME_DIR / "Local State"
        if not local_state.exists():
            return []
        data = json.loads(local_state.read_text())
        info = (data.get("profile") or {}).get("info_cache", {})
        out = [cls(folder=k, display_name=(v.get("name") or k)) for k, v in info.items()]
        out.sort(key=lambda p: p.folder)
        return out

    @classmethod
    def resolve(cls, hint: str | None) -> "ChromeProfile":
        """Resolve by folder name *or* display name. Default → "Default" folder."""
        if not hint:
            hint = "Default"
        profiles = cls.list()
        for p in profiles:
            if p.folder == hint or p.display_name == hint:
                return p
        # Allow path-style: "Profile 1"
        path = CHROME_DIR / hint
        if path.exists():
            return cls(folder=hint, display_name=hint)
        raise ValueError(
            f"Chrome profile {hint!r} not found. "
            f"Available: {[p.display_name + ' (' + p.folder + ')' for p in profiles]}"
        )

    @property
    def cookies_path(self) -> pathlib.Path:
        return CHROME_DIR / self.folder / "Cookies"

    def cookies_for(self, domain: str) -> list:
        cj = browser_cookie3.chrome(domain_name=domain, cookie_file=str(self.cookies_path))
        return list(cj)


def cookies_to_playwright(
    cookies: Iterable, *, skip: Iterable[str] = ()
) -> list[dict]:
    """Convert a cookielib jar to Playwright's add_cookies() format.

    `skip` is a list of cookie-name prefixes to drop (typically the
    fingerprint-bound bot-defense tokens that don't survive replay).
    """
    skip_tuple = tuple(skip)
    out = []
    for c in cookies:
        if any(c.name == p or c.name.startswith(p) for p in skip_tuple):
            continue
        out.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain if c.domain.startswith(".") else "." + c.domain.lstrip("."),
            "path": c.path or "/",
            "secure": bool(c.secure),
            "sameSite": "Lax",
        })
    return out


class BrowserSession:
    """Context manager around a Playwright Chromium with cookies preloaded."""

    def __init__(
        self,
        *,
        profile: ChromeProfile,
        domain: str,
        skip_cookies: Iterable[str] = (),
        headless: bool = False,
        viewport: tuple[int, int] = (1440, 1000),
        user_agent: str = DEFAULT_UA,
    ):
        self.profile = profile
        self.domain = domain
        self.skip_cookies = list(skip_cookies)
        self.headless = headless
        self.viewport = viewport
        self.user_agent = user_agent
        self._pw = None
        self._browser = None
        self._ctx = None

    def __enter__(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._ctx = self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            user_agent=self.user_agent,
            locale="en-US",
        )
        self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        cookies = self.profile.cookies_for(self.domain)
        pw_cookies = cookies_to_playwright(cookies, skip=self.skip_cookies)
        if pw_cookies:
            self._ctx.add_cookies(pw_cookies)
        print(
            f"[browser] domain={self.domain} profile={self.profile.display_name} "
            f"({self.profile.folder}) cookies injected={len(pw_cookies)}",
            file=sys.stderr,
        )
        return self

    def __exit__(self, *exc):
        with contextlib.suppress(Exception):
            self._browser.close()
        with contextlib.suppress(Exception):
            self._pw.stop()

    # Convenience pass-throughs
    def new_page(self):
        return self._ctx.new_page()

    @property
    def request(self):
        return self._ctx.request


@contextlib.contextmanager
def captured_response(page, url_pattern: str, method: str = "POST", timeout_ms: int = 60000) -> Iterator:
    """Yield a Playwright `Response` whose URL contains `url_pattern`."""
    with page.expect_response(
        lambda r: url_pattern in r.url and r.request.method == method,
        timeout=timeout_ms,
    ) as info:
        yield info
