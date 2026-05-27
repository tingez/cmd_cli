"""Seeking Alpha screener: e.g. 'Top Rated Stocks' (id 96793299).

Flow: open the screener page in the user's Chrome (so PerimeterX issues
fresh tokens), capture the `/api/v3/screener_results` POST to discover the
exact filter body, replay it with a bumped page size, then call
`/api/v3/metrics` to enrich each ticker with quant/authors/sell-side
ratings and market cap.
"""
from __future__ import annotations

import json
import sys
import time

from ...browser import BrowserSession, ChromeProfile, captured_response
from ...errors import BotBlockedError, ParseError
from ...registry import Arg, Strategy, cli
from .common import DOMAIN, SKIP_COOKIES

URL_TMPL = "https://seekingalpha.com/screeners/{screener_id}-Top-Rated-Stocks"
API_RESULTS = "https://seekingalpha.com/api/v3/screener_results"
API_METRICS = "https://seekingalpha.com/api/v3/metrics"

COLUMNS = ["Symbol", "Company", "Exchange",
           "Quant Rating", "Quant Score",
           "Authors Rating", "Authors Score",
           "Sell-side Rating", "Sell-side Score",
           "Market Cap", "URL"]


def _rating_label(v):
    if v is None:
        return ""
    v = float(v)
    if v >= 4.5: return "Strong Buy"
    if v >= 3.5: return "Buy"
    if v >= 2.5: return "Hold"
    if v >= 1.5: return "Sell"
    return "Strong Sell"


def _fmt_mc(v):
    if v is None:
        return ""
    v = float(v)
    if v >= 1e12: return f"${v / 1e12:.2f}T"
    if v >= 1e9:  return f"${v / 1e9:.2f}B"
    if v >= 1e6:  return f"${v / 1e6:.2f}M"
    return f"${v:,.0f}"


def _bump_page_size(body: dict, size: int) -> dict:
    if isinstance(body.get("page"), dict):
        body["page"]["size"] = size
        body["page"]["number"] = 1
    elif isinstance(body.get("pagination"), dict):
        body["pagination"]["per_page"] = size
        body["pagination"]["page"] = 1
    elif "per_page" in body:
        body["per_page"] = size
    else:
        body["page"] = {"size": size, "number": 1}
    return body


def _index_metrics(payload: dict) -> dict:
    metric_types = {m["id"]: m["attributes"].get("field")
                    for m in payload.get("included", [])
                    if m.get("type") == "metric_type"}
    tickers_idx = {inc["id"]: inc["attributes"].get("slug", "").lower()
                   for inc in payload.get("included", [])
                   if inc.get("type") == "ticker"}
    out: dict = {}
    for d in payload.get("data", []):
        rels = d["relationships"]
        t_id = rels.get("ticker", {}).get("data", {}).get("id")
        m_id = rels.get("metric_type", {}).get("data", {}).get("id")
        slug = tickers_idx.get(t_id)
        field = metric_types.get(m_id)
        if not slug or not field:
            continue
        out.setdefault(slug, {})[field] = d["attributes"].get("value")
    return out


@cli(
    site="seekingalpha",
    name="top-rated",
    description="Seeking Alpha screener — Top Rated Stocks (cross-filter: quant + authors + sell-side)",
    strategy=Strategy.AUTHED_BROWSER,
    domain=DOMAIN,
    columns=COLUMNS,
    args=[
        Arg("profile", default="Default",
            help="Chrome profile display name (e.g. 'Person 1' / 'Default' / 'Profile 1')"),
        Arg("screener_id", default="96793299",
            help="Seeking Alpha screener ID (visit /screeners/<id>-... to find)"),
        Arg("page_size", type=int, default=500,
            help="Replay POST page size (cap on number of rows)"),
        Arg("headless", type=bool, default=False,
            help="Run Chromium headless (PerimeterX may block)"),
        Arg("timeout", type=int, default=60,
            help="Page-load timeout in seconds"),
    ],
)
def fetch(profile: str, screener_id: str, page_size: int,
          headless: bool, timeout: int) -> list[dict]:
    prof = ChromeProfile.resolve(profile)
    url = URL_TMPL.format(screener_id=screener_id)
    with BrowserSession(
        profile=prof, domain=DOMAIN, skip_cookies=SKIP_COOKIES, headless=headless,
    ) as sess:
        page = sess.new_page()
        print(f"[sa/top-rated] navigating to {url}", file=sys.stderr)

        # Capture the original screener_results POST while page loads
        with captured_response(page, "/api/v3/screener_results", "POST",
                               timeout_ms=timeout * 1000) as info:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        resp = info.value
        req = resp.request
        body_text = req.post_data
        if not body_text:
            raise ParseError("screener_results POST had no body")

        body = json.loads(body_text)
        body = _bump_page_size(body, page_size)

        # Replay through the browser's request context (preserves cookies +
        # PerimeterX state). Strip headers that must be set per-request.
        headers = {k: v for k, v in dict(req.headers).items()
                   if k.lower() not in ("content-length", "host", "cookie")}
        replay = sess.request.post(resp.url, data=json.dumps(body), headers=headers)
        if not replay.ok:
            raise BotBlockedError(f"replay POST status={replay.status}")
        screener_data = replay.json()
        if not isinstance(screener_data.get("data"), list):
            raise ParseError("unexpected screener_results shape")

        tickers = []
        for item in screener_data["data"]:
            a = item.get("attributes", {})
            tickers.append({
                "slug": (a.get("slug") or "").lower(),
                "symbol": a.get("name", ""),
                "company": a.get("company", ""),
                "exchange": a.get("exchange", ""),
            })
        slugs = [t["slug"] for t in tickers if t["slug"]]
        if not slugs:
            return []

        # Enrich with metrics
        slug_csv = "%2C".join(slugs)
        metrics_url = (f"{API_METRICS}"
                       "?filter[fields]=authors_rating,quant_rating,sell_side_rating,marketcap"
                       f"&filter[slugs]={slug_csv}")
        mresp = sess.request.get(metrics_url,
                                 headers={"Accept": "application/json",
                                          "Referer": url})
        m_idx = _index_metrics(mresp.json()) if mresp.ok else {}
        time.sleep(0.5)  # let the browser fully settle before close

    rows = []
    for t in tickers:
        m = m_idx.get(t["slug"], {})
        rows.append({
            "Symbol":   t["symbol"],
            "Company":  t["company"],
            "Exchange": t["exchange"],
            "Quant Rating":     _rating_label(m.get("quant_rating")),
            "Quant Score":      round(float(m["quant_rating"]), 2) if m.get("quant_rating") else "",
            "Authors Rating":   _rating_label(m.get("authors_rating")),
            "Authors Score":    round(float(m["authors_rating"]), 2) if m.get("authors_rating") else "",
            "Sell-side Rating": _rating_label(m.get("sell_side_rating")),
            "Sell-side Score":  round(float(m["sell_side_rating"]), 2) if m.get("sell_side_rating") else "",
            "Market Cap":       _fmt_mc(m.get("marketcap")),
            "Market Cap Raw":   m.get("marketcap") or "",
            "URL": f"https://seekingalpha.com/symbol/{t['symbol']}",
        })
    rows.sort(key=lambda r: -float(r["Quant Score"]) if r["Quant Score"] != "" else 0)
    return rows
