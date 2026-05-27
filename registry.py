"""Registry + @cli decorator. Mirrors the OpenCLI pattern in Python.

Each scraper is a callable registered with metadata so the CLI runner can:
- discover it (`list`, `list <site>`)
- validate args declaratively
- format output uniformly (columns)
- choose the right execution strategy (public HTTP vs. authed browser)
"""
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Callable


class Strategy(enum.Enum):
    """How a task gets its data."""

    PUBLIC_HTTP = "public_http"          # no auth, plain HTTP
    PUBLIC_BROWSER = "public_browser"    # JS-rendered, no login
    AUTHED_HTTP = "authed_http"          # cookies from Chrome, no JS
    AUTHED_BROWSER = "authed_browser"    # cookies from Chrome + Playwright (handles bot defense)


@dataclasses.dataclass
class Arg:
    """Declarative argument metadata. Mirrors OpenCLI's args[]."""

    name: str
    type: type = str
    default: Any = None
    required: bool = False
    help: str = ""
    choices: list[Any] | None = None


@dataclasses.dataclass
class Task:
    site: str
    name: str
    description: str
    func: Callable[..., list[dict]]
    strategy: Strategy = Strategy.PUBLIC_HTTP
    args: list[Arg] = dataclasses.field(default_factory=list)
    columns: list[str] | None = None       # preferred column order for table/CSV
    domain: str | None = None              # cookie domain (e.g. "zacks.com")

    @property
    def qualified_name(self) -> str:
        return f"{self.site}/{self.name}"

    def call(self, **kwargs) -> list[dict]:
        # Fill defaults + basic validation
        params = {}
        for a in self.args:
            v = kwargs.get(a.name, a.default)
            if a.required and v is None:
                from .errors import ArgumentError
                raise ArgumentError(f"missing required argument: --{a.name}")
            if v is not None and a.choices and v not in a.choices:
                from .errors import ArgumentError
                raise ArgumentError(
                    f"--{a.name}={v!r} not in choices {a.choices}"
                )
            params[a.name] = v
        return self.func(**params)


class Registry:
    """Process-global registry. Source modules import this and call @cli."""

    _tasks: dict[str, Task] = {}

    @classmethod
    def register(cls, task: Task) -> None:
        key = task.qualified_name
        if key in cls._tasks:
            raise ValueError(f"task {key!r} already registered")
        cls._tasks[key] = task

    @classmethod
    def get(cls, qualified_name: str) -> Task:
        if qualified_name not in cls._tasks:
            raise KeyError(f"unknown task {qualified_name!r}")
        return cls._tasks[qualified_name]

    @classmethod
    def all(cls) -> list[Task]:
        return sorted(cls._tasks.values(), key=lambda t: (t.site, t.name))

    @classmethod
    def sites(cls) -> list[str]:
        return sorted({t.site for t in cls._tasks.values()})

    @classmethod
    def for_site(cls, site: str) -> list[Task]:
        return [t for t in cls.all() if t.site == site]


def cli(
    *,
    site: str,
    name: str,
    description: str = "",
    strategy: Strategy = Strategy.PUBLIC_HTTP,
    args: list[Arg] | None = None,
    columns: list[str] | None = None,
    domain: str | None = None,
):
    """Decorator: register a scraper function as a CLI-callable task."""

    def wrap(func: Callable[..., list[dict]]) -> Callable[..., list[dict]]:
        Registry.register(
            Task(
                site=site,
                name=name,
                description=description or func.__doc__ or "",
                func=func,
                strategy=strategy,
                args=list(args or []),
                columns=columns,
                domain=domain,
            )
        )
        return func

    return wrap
