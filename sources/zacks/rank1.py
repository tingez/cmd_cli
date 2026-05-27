"""Zacks #1 Rank Strong Buy list (Zacks Premium feature)."""
from __future__ import annotations

import re
import sys
import time

from bs4 import BeautifulSoup

from ...browser import BrowserSession, ChromeProfile
from ...errors import BotBlockedError, ParseError
from ...registry import Arg, Strategy, cli
from .common import DOMAIN, SKIP_COOKIES

URL = (
    "https://www.zacks.com/stocks/buy-list/"
    "?adid=zp_topnav_1list&icid=quote-stock_overview-nav_tracking-zacks_premium"
    "-main_menu_wrapper-zacks_1_rank"
)
TABLE_ID = "full_one_list_table_full_one_list"

COLUMNS = ["Symbol", "Company", "Industry", "Price", "Date Added",
           "Market Cap (Mil)", "Value Score", "Growth Score",
           "Momentum Score", "VGM Score", "URL"]


def _parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", id=TABLE_ID)
    if not table:
        raise ParseError(
            f"table#{TABLE_ID} not found — markup may have changed or login expired"
        )
    rows = table.find_all("tr")
    headers = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    out = []
    for tr in rows[1:]:
        cells = tr.find_all(["th", "td"])
        if len(cells) != len(headers):
            continue
        row: dict = {}
        for h, c in zip(headers, cells):
            text = c.get_text(" ", strip=True)
            if h == "Symbol":
                text = text.split()[0] if text else text
            row[h] = text
        a = tr.find("a", href=re.compile(r"/stock/quote/"))
        if a:
            href = a.get("href", "")
            row["URL"] = "https:" + href if href.startswith("//") else href
        out.append(row)
    return out


@cli(
    site="zacks",
    name="rank1",
    description="Zacks #1 Rank Strong Buy list (requires Zacks Premium login)",
    strategy=Strategy.AUTHED_BROWSER,
    domain=DOMAIN,
    columns=COLUMNS,
    args=[
        Arg("profile", default="Default",
            help="Chrome profile display name or folder (e.g. 'Person 1' / 'Profile 1' / 'Default')"),
        Arg("headless", type=bool, default=False,
            help="Run Chromium headless (may trigger Imperva)"),
        Arg("timeout", type=int, default=60,
            help="Page-load timeout in seconds"),
    ],
)
def fetch(profile: str, headless: bool, timeout: int) -> list[dict]:
    prof = ChromeProfile.resolve(profile)
    with BrowserSession(
        profile=prof, domain=DOMAIN, skip_cookies=SKIP_COOKIES, headless=headless,
    ) as sess:
        page = sess.new_page()
        print(f"[zacks/rank1] navigating to {URL}", file=sys.stderr)
        page.goto(URL, wait_until="domcontentloaded", timeout=timeout * 1000)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            title = page.title()
            if "Pardon Our Interruption" in title:
                continue
            if len(page.content()) > 30000:
                break
        title = page.title()
        if "Pardon Our Interruption" in title:
            raise BotBlockedError("Imperva still blocking after timeout")
        try:
            page.wait_for_selector(f"table#{TABLE_ID}", timeout=10000)
        except Exception:
            pass
        time.sleep(2)
        html = page.content()
    return _parse(html)
