"""`ready` command: report the worker's environment so the plugin can explain
a broken installation with the exact remedy instead of a stack trace."""

from __future__ import annotations

import importlib
import platform
import sys
from typing import Any

from . import __version__

PACKAGES = ("skrf", "numpy", "scipy", "matplotlib")


def run(_payload: dict[str, Any]) -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            module = importlib.import_module(name)
            packages[name] = str(getattr(module, "__version__", "unknown"))
        except ImportError:
            packages[name] = None
    return {
        "worker_version": __version__,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "packages": packages,
        "ready": all(v is not None for v in packages.values()),
    }
