"""Entry point: one JSON request on stdin, one JSON response on stdout.

stdout carries exactly one JSON document; everything else (matplotlib
warnings, scikit-rf chatter, our own logs) goes to stderr, which the
TypeScript side caps and attaches to error messages.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from .protocol import COMMANDS, PROTOCOL_VERSION, WorkerError, fail, ok


def _apply_limits(limits: dict[str, Any]) -> None:
    """Cap the worker's own address space. ctx.subprocess offers no rlimits,
    so the worker enforces the plugin's `maxMemoryMb` on itself."""
    max_memory_mb = limits.get("max_memory_mb")
    if not max_memory_mb:
        return
    try:
        import resource

        cap = int(max_memory_mb) * 1024 * 1024
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = cap if hard == resource.RLIM_INFINITY else min(cap, hard)
        resource.setrlimit(resource.RLIMIT_AS, (min(cap, new_hard), new_hard))
    except (ImportError, ValueError, OSError) as exc:  # Windows, or cap below current use
        print(f"dsh_si: could not apply memory limit: {exc}", file=sys.stderr)


def _dispatch(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    if command == "ready":
        from .ready import run
    elif command == "inspect":
        from .inspect import run
    elif command == "analyze":
        from .analyze import run
    else:  # pragma: no cover - guarded by the caller
        raise WorkerError("unsupported_command", f"unsupported command {command!r}")
    return run(payload)


def main(stdin: Any = sys.stdin, stdout: Any = sys.stdout) -> int:
    raw = stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit(stdout, fail("bad_request", f"request is not valid JSON: {exc}"))
        return 2
    if not isinstance(request, dict):
        _emit(stdout, fail("bad_request", "request must be a JSON object"))
        return 2
    if request.get("protocol") != PROTOCOL_VERSION:
        _emit(
            stdout,
            fail(
                "bad_request",
                f"protocol mismatch: worker speaks v{PROTOCOL_VERSION}, "
                f"request is v{request.get('protocol')!r}",
            ),
        )
        return 2
    command = request.get("command")
    if command not in COMMANDS:
        _emit(stdout, fail("unsupported_command", f"unsupported command {command!r}"))
        return 2
    payload = request.get("payload") or {}
    if not isinstance(payload, dict):
        _emit(stdout, fail("bad_request", "payload must be a JSON object"))
        return 2
    _apply_limits(request.get("limits") or {})
    try:
        result = _dispatch(command, payload)
    except WorkerError as exc:
        _emit(stdout, fail(exc.code, exc.message, exc.detail))
        return 1
    except MemoryError:
        _emit(stdout, fail("numerical_error", "worker exceeded its memory limit"))
        return 1
    except Exception as exc:  # noqa: BLE001 - last resort; must still answer with JSON
        _emit(stdout, fail("internal", f"{type(exc).__name__}: {exc}", traceback.format_exc()))
        return 1
    _emit(stdout, ok(result))
    return 0


def _emit(stdout: Any, document: dict[str, Any]) -> None:
    stdout.write(json.dumps(document, allow_nan=False))
    stdout.write("\n")
    stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
