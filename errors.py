"""Typed exceptions used across sources and the CLI runner."""


class StockCLIError(Exception):
    """Base exception."""


class ArgumentError(StockCLIError):
    """A task was called with an invalid argument value."""


class AuthRequiredError(StockCLIError):
    """The Chrome profile doesn't have the cookies needed to satisfy auth."""


class BotBlockedError(StockCLIError):
    """A bot-detection interstitial (Imperva, Cloudflare, PerimeterX) blocked us."""


class ParseError(StockCLIError):
    """The page loaded but didn't contain the expected structure."""


class EmptyResultError(StockCLIError):
    """Task ran cleanly but the result set is empty."""
