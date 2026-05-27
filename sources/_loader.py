"""Import every source package so their @cli decorators run.

Adding a new source: drop a `stockcli/sources/<name>/__init__.py` that
imports its task modules. Then add `from . import <name>` here.
"""
from . import zacks  # noqa: F401
from . import tipranks  # noqa: F401
from . import seekingalpha  # noqa: F401
