"""Optional TOML config (~/.stockcli/config.toml) for per-site defaults.

Example:

    [defaults]
    profile = "MyProfile"
    output_dir = "~/data/stocks"

    [zacks.rank1]
    # override default for one task
    output_dir = "~/data/zacks"

    [seekingalpha.top_rated]
    screener_id = "96793299"
"""
from __future__ import annotations

import os
import pathlib
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

CONFIG_PATH = pathlib.Path(os.environ.get("STOCKCLI_CONFIG", "~/.stockcli/config.toml")).expanduser()


def load() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return tomllib.loads(CONFIG_PATH.read_text())


def resolve_defaults(cfg: dict, site: str, name: str) -> dict:
    """Merge [defaults] + [site.name] into a flat dict of default values."""
    out = dict(cfg.get("defaults", {}))
    out.update((cfg.get(site, {}) or {}).get(name, {}) or {})
    return out
