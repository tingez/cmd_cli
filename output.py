"""Output formatters: json, csv, pretty table."""
from __future__ import annotations

import csv
import json
import pathlib
import sys

from rich.console import Console
from rich.table import Table


def _columns(rows: list[dict], preferred: list[str] | None) -> list[str]:
    if not rows:
        return preferred or []
    if preferred:
        rest = [k for k in rows[0].keys() if k not in preferred]
        return [c for c in preferred if c in rows[0]] + rest
    return list(rows[0].keys())


def write_json(rows: list[dict], path: pathlib.Path) -> None:
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False))


def write_csv(rows: list[dict], path: pathlib.Path, *, columns: list[str] | None = None) -> None:
    cols = _columns(rows, columns)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def print_table(
    rows: list[dict],
    *,
    columns: list[str] | None = None,
    title: str | None = None,
    limit: int | None = 25,
) -> None:
    console = Console(stderr=False)
    if not rows:
        console.print("[yellow](no rows)[/]")
        return
    cols = _columns(rows, columns)
    # Drop URL-ish + obviously-raw columns from the table preview.
    SKIP_SUFFIXES = ("URL", "Raw", "Abs")
    table_cols = [c for c in cols
                  if not any(c.lower().endswith(s.lower()) for s in SKIP_SUFFIXES)]
    # Cap to the first 8 columns — enough for an at-a-glance view; full
    # data is always available via --format csv / --format json.
    MAX_TABLE_COLS = 8
    if len(table_cols) > MAX_TABLE_COLS:
        table_cols = table_cols[:MAX_TABLE_COLS]
    table = Table(title=title, show_lines=False, header_style="bold cyan")
    for c in table_cols:
        table.add_column(c, overflow="ellipsis", max_width=22)
    shown = rows if limit is None else rows[:limit]
    for r in shown:
        table.add_row(*[str(r.get(c, "")) for c in table_cols])
    console.print(table)
    if limit is not None and len(rows) > limit:
        console.print(
            f"[dim]... {len(rows) - limit} more rows hidden "
            f"(use --limit 0 to show all)[/]"
        )


def emit(
    rows: list[dict],
    *,
    fmt: str,
    out: pathlib.Path | None,
    columns: list[str] | None,
    title: str | None = None,
    limit: int | None = 25,
) -> None:
    """Single entrypoint used by the CLI runner."""
    if fmt == "json":
        if out:
            write_json(rows, out)
            print(f"wrote {out} ({len(rows)} rows)", file=sys.stderr)
        else:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
    elif fmt == "csv":
        if out:
            write_csv(rows, out, columns=columns)
            print(f"wrote {out} ({len(rows)} rows)", file=sys.stderr)
        else:
            import io
            buf = io.StringIO()
            cols = _columns(rows, columns)
            w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)
            print(buf.getvalue())
    elif fmt == "table":
        print_table(rows, columns=columns, title=title, limit=limit)
        if out:
            # When user asks for table + an output file, also drop CSV/JSON
            # based on the file extension.
            if out.suffix.lower() == ".json":
                write_json(rows, out)
            else:
                write_csv(rows, out, columns=columns)
            print(f"wrote {out} ({len(rows)} rows)", file=sys.stderr)
    else:
        raise ValueError(f"unknown format {fmt!r}")
