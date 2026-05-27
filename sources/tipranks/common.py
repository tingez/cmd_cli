"""Shared TipRanks constants."""
DOMAIN = "tipranks.com"

# Cloudflare-managed tokens — let them regenerate naturally.
SKIP_COOKIES = ("__cf_bm", "cf_clearance")

CONSENSUS_MAP = {
    "strongBuy": "Strong Buy",
    "moderateBuy": "Moderate Buy",
    "hold": "Hold",
    "moderateSell": "Moderate Sell",
    "strongSell": "Strong Sell",
    "buy": "Buy",
    "sell": "Sell",
}


def fmt_market_cap(v):
    if v is None:
        return ""
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"${v:,.0f}"
