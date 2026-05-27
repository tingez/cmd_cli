"""TipRanks Analysts' Top Stocks screener.

Uses the static CDN payload `tr-cdn.tipranks.com/.../payload.json` — no
auth, no Cloudflare. Returns the full screener at once.
"""
from __future__ import annotations

from ...http import fetch_json
from ...registry import Arg, Strategy, cli
from .common import CONSENSUS_MAP, DOMAIN, fmt_market_cap

# Each TipRanks screener has its own JSON payload URL.
SCREENERS = {
    "analysts-top-stocks": "https://tr-cdn.tipranks.com/research/prod/screener/analysts-top-stocks/payload.json",
    "top-smart-score-stocks": "https://tr-cdn.tipranks.com/research/prod/screener/top-smart-score-stocks/payload.json",
}

COLUMNS = ["Ticker", "Company", "Sector", "Market", "Price", "Price Target",
           "Upside %", "Stock Rating", "Smart Score", "Change %", "Market Cap",
           "Analyst Buys", "Analyst Holds", "Analyst Sells", "URL"]


def _flatten(stocks: list[dict]) -> list[dict]:
    out = []
    for s in stocks:
        ticker = s.get("ticker", "")
        price = s.get("price")
        ar = s.get("analystRatings") or {}
        pt = (ar.get("bestConsensus") or {}).get("priceTarget", {}).get("value")
        cons = (ar.get("consensus") or {}).get("id", "")
        chg = s.get("change") or {}
        reasoning = ar.get("ratingReasoning") or []
        buys = next((r["analystsCount"] for r in reasoning if r.get("rating") == "buy"), 0)
        holds = next((r["analystsCount"] for r in reasoning if r.get("rating") == "hold"), 0)
        sells = next((r["analystsCount"] for r in reasoning if r.get("rating") == "sell"), 0)
        upside = ((pt / price - 1) * 100) if (pt is not None and price) else None
        ss = (s.get("smartScore") or {}).get("value")
        out.append({
            "Ticker": ticker,
            "Company": s.get("name", ""),
            "Sector": s.get("sector", ""),
            "Market": s.get("market", ""),
            "Price": f"{price:.2f}" if price is not None else "",
            "Price Target": f"{pt:.2f}" if pt is not None else "",
            "Upside %": f"{upside:.2f}" if upside is not None else "",
            "Stock Rating": CONSENSUS_MAP.get(cons, cons),
            "Smart Score": f"{ss:.2f}" if ss is not None else "",
            "Change %": f"{chg.get('percent'):.2f}" if chg.get("percent") is not None else "",
            "Change Abs": f"{chg.get('amount'):.4f}" if chg.get("amount") is not None else "",
            "Market Cap": fmt_market_cap(s.get("marketCap")),
            "Market Cap Raw": s.get("marketCap") or "",
            "Analyst Buys": buys,
            "Analyst Holds": holds,
            "Analyst Sells": sells,
            "URL": f"https://www.tipranks.com/stocks/{ticker.lower()}/forecast",
        })
    out.sort(key=lambda r: -float(r["Upside %"]) if r["Upside %"] else 0)
    return out


@cli(
    site="tipranks",
    name="top-stocks",
    description="TipRanks screener payload (no login required)",
    strategy=Strategy.PUBLIC_HTTP,
    domain=DOMAIN,
    columns=COLUMNS,
    args=[
        Arg("screener", default="analysts-top-stocks",
            choices=list(SCREENERS.keys()),
            help="TipRanks screener slug"),
        Arg("min_market_cap", type=float, default=None,
            help="Drop tickers with market cap below this many USD"),
        Arg("sector", default=None,
            help="Filter to this sector (e.g. 'healthcare', 'technology')"),
    ],
)
def fetch(screener: str, min_market_cap: float | None, sector: str | None) -> list[dict]:
    url = SCREENERS[screener]
    payload = fetch_json(
        url,
        headers={"Referer": "https://www.tipranks.com/"},
    )
    stocks = payload["TopRatedStocks"]["data"]["stocks"]
    rows = _flatten(stocks)
    if min_market_cap is not None:
        rows = [r for r in rows
                if r["Market Cap Raw"] and float(r["Market Cap Raw"]) >= min_market_cap]
    if sector:
        rows = [r for r in rows if (r["Sector"] or "").lower() == sector.lower()]
    return rows
