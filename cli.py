"""Typer-based CLI entrypoint.

Commands:
    stockcli list                    # list all sites
    stockcli list <site>             # list tasks for a site
    stockcli profiles                # list Chrome profiles
    stockcli fetch <site>/<task>     # run one scraper
    stockcli intersect <a> <b>...    # intersect rows across multiple tasks
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import config as _config
from . import output as _output
from .browser import CHROME_DIR, ChromeProfile
from .registry import Registry
from .sources import _loader  # noqa: F401 — triggers @cli registration

app = typer.Typer(
    add_completion=False,
    help="Plugin-based CLI for scraping rated-stock lists. "
         "Add a new site under stockcli/sources/<name>/.",
)
console = Console()


# ---------- helpers ----------
def _split_qname(qname: str) -> tuple[str, str]:
    if "/" not in qname:
        raise typer.BadParameter(
            f"task name must be '<site>/<task>', got {qname!r}"
        )
    site, name = qname.split("/", 1)
    return site, name


def _coerce(value: str, type_: type):
    if type_ is bool:
        return str(value).lower() in ("1", "true", "yes", "y", "on")
    if type_ is int:
        return int(value)
    if type_ is float:
        return float(value)
    return value


def _parse_extra_args(extras: list[str]) -> dict:
    """Parse trailing `--key value` / `--key=value` / `--flag` into a dict."""
    out: dict = {}
    i = 0
    while i < len(extras):
        tok = extras[i]
        if not tok.startswith("--"):
            raise typer.BadParameter(f"unexpected positional arg {tok!r}")
        key = tok[2:]
        if "=" in key:
            k, v = key.split("=", 1)
            out[k.replace("-", "_")] = v
            i += 1
        elif i + 1 < len(extras) and not extras[i + 1].startswith("--"):
            out[key.replace("-", "_")] = extras[i + 1]
            i += 2
        else:
            out[key.replace("-", "_")] = "true"
            i += 1
    return out


# ---------- commands ----------
@app.command("list")
def list_cmd(site: Optional[str] = typer.Argument(None, help="Filter to one site")):
    """List available sites and tasks."""
    tasks = Registry.for_site(site) if site else Registry.all()
    if not tasks:
        console.print(f"[yellow]no tasks registered{' for ' + site if site else ''}[/]")
        raise typer.Exit(1)
    table = Table(title="Available tasks", header_style="bold cyan")
    table.add_column("Qualified"); table.add_column("Strategy")
    table.add_column("Args"); table.add_column("Description")
    for t in tasks:
        args = ", ".join(
            f"{a.name}={a.default!r}" + (" *" if a.required else "")
            for a in t.args
        )
        table.add_row(t.qualified_name, t.strategy.value, args, t.description)
    console.print(table)


@app.command("profiles")
def profiles_cmd():
    """List Chrome profiles available for cookie loading."""
    profiles = ChromeProfile.list()
    if not profiles:
        console.print(f"[red]No Chrome profiles found at {CHROME_DIR}[/]")
        raise typer.Exit(1)
    table = Table(title="Chrome profiles", header_style="bold cyan")
    table.add_column("Display name"); table.add_column("Folder")
    table.add_column("Cookies path"); table.add_column("Exists?")
    for p in profiles:
        table.add_row(p.display_name, p.folder, str(p.cookies_path),
                      "yes" if p.cookies_path.exists() else "no")
    console.print(table)


@app.command(
    "fetch",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def fetch_cmd(
    ctx: typer.Context,
    qname: str = typer.Argument(..., help="Task name e.g. zacks/rank1"),
    fmt: str = typer.Option("table", "--format", "-f",
                            help="table | json | csv"),
    out: Optional[pathlib.Path] = typer.Option(None, "--out", "-o",
                                               help="Write to this file"),
    limit: int = typer.Option(25, "--limit",
                              help="Rows shown in table format (use 0 for all)"),
):
    """Run a scraper. Extra `--key value` args are forwarded to the task.

    Example:
        stockcli fetch tipranks/top-stocks --min-market-cap 10e9 --sector technology
    """
    cfg = _config.load()
    site, name = _split_qname(qname)
    task = Registry.get(qname)

    # Merge: task defaults <- config defaults <- CLI extras
    extras = _parse_extra_args(ctx.args)
    params: dict = {}
    file_defaults = _config.resolve_defaults(cfg, site, name.replace("-", "_"))
    for a in task.args:
        if a.name in extras:
            params[a.name] = _coerce(extras[a.name], a.type)
        elif a.name in file_defaults:
            params[a.name] = _coerce(str(file_defaults[a.name]), a.type)
        else:
            params[a.name] = a.default

    print(f"[stockcli] running {qname} with {params}", file=sys.stderr)
    rows = task.call(**params)
    print(f"[stockcli] got {len(rows)} rows", file=sys.stderr)

    _output.emit(
        rows,
        fmt=fmt,
        out=out,
        columns=task.columns,
        title=qname,
        limit=None if limit == 0 else limit,
    )


@app.command("intersect")
def intersect_cmd(
    inputs: list[str] = typer.Argument(
        ..., help="JSON files OR <site>/<task> to run inline"),
    key: str = typer.Option(
        None, "--key",
        help="Field name to intersect on (auto-detected if omitted)"),
    out: Optional[pathlib.Path] = typer.Option(None, "--out", "-o"),
    fmt: str = typer.Option("table", "--format", "-f"),
):
    """Intersect rows from multiple sources by a common key (e.g. Symbol)."""
    # Default field-name guesses per common ticker column name
    AUTO_KEYS = ["Symbol", "Ticker", "ticker", "symbol"]

    datasets: list[tuple[str, list[dict]]] = []
    for inp in inputs:
        if pathlib.Path(inp).exists():
            data = json.loads(pathlib.Path(inp).read_text())
            datasets.append((inp, data))
        else:
            task = Registry.get(inp)
            print(f"[intersect] running {inp}...", file=sys.stderr)
            datasets.append((inp, task.call(
                **{a.name: a.default for a in task.args}
            )))

    def _key_in(row: dict) -> str | None:
        if key:
            return str(row.get(key, "")).upper().split()[0] or None
        for k in AUTO_KEYS:
            if k in row:
                return str(row[k]).upper().split()[0] or None
        return None

    sets = []
    indices = []
    for label, rows in datasets:
        idx: dict = {}
        for r in rows:
            tk = _key_in(r)
            if tk:
                idx.setdefault(tk, r)
        indices.append(idx)
        sets.append(set(idx))
        print(f"  {label}: {len(idx)} unique tickers", file=sys.stderr)

    common = sorted(set.intersection(*sets)) if sets else []
    print(f"[intersect] {len(common)} tickers in all "
          f"{len(datasets)} sources", file=sys.stderr)

    merged = []
    for tk in common:
        row = {"Ticker": tk}
        for (label, _), idx in zip(datasets, indices):
            tag = label.replace("/", "_")
            for k, v in (idx.get(tk) or {}).items():
                row[f"{tag}::{k}"] = v
        merged.append(row)

    _output.emit(merged, fmt=fmt, out=out,
                 columns=["Ticker"], title="Intersection", limit=50)
