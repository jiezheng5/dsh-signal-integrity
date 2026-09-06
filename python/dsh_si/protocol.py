"""Wire contract shared with the TypeScript side (src/protocol.ts).

The TypeScript test suite spawns this module and asserts these constants match
its own copy, so change both files together.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

PROTOCOL_VERSION = 1

Command = Literal["ready", "inspect", "analyze"]
COMMANDS: tuple[Command, ...] = ("ready", "inspect", "analyze")


class Limits(TypedDict, total=False):
    """Resource limits applied by the worker to itself before doing work."""

    max_memory_mb: int


class Request(TypedDict):
    protocol: int
    command: Command
    payload: dict[str, Any]
    limits: Limits


class ErrorInfo(TypedDict, total=False):
    code: str
    message: str
    detail: str


# Error codes the TypeScript side matches on. Keep in sync with src/protocol.ts.
ERROR_CODES: tuple[str, ...] = (
    "bad_request",
    "unsupported_command",
    "file_not_found",
    "parse_error",
    "unsupported_format",
    "interpretation_invalid",
    "hash_mismatch",
    "numerical_error",
    "report_write_failed",
    "internal",
)


def ok(result: dict[str, Any]) -> dict[str, Any]:
    return {"protocol": PROTOCOL_VERSION, "ok": True, "result": result}


def fail(code: str, message: str, detail: str | None = None) -> dict[str, Any]:
    if code not in ERROR_CODES:
        raise ValueError(f"unknown error code {code!r}")
    error: ErrorInfo = {"code": code, "message": message}
    if detail is not None:
        error["detail"] = detail
    return {"protocol": PROTOCOL_VERSION, "ok": False, "error": error}


class WorkerError(Exception):
    """A domain failure the worker reports as a structured error, not a crash."""

    def __init__(self, code: str, message: str, detail: str | None = None) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.detail = detail
