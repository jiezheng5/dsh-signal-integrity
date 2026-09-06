import io
import json

from dsh_si.__main__ import main
from dsh_si.protocol import PROTOCOL_VERSION


def _run(request) -> tuple[int, dict]:
    out = io.StringIO()
    code = main(
        stdin=io.StringIO(json.dumps(request) if not isinstance(request, str) else request),
        stdout=out,
    )
    lines = out.getvalue().splitlines()
    assert len(lines) == 1, "worker must emit exactly one JSON line on stdout"
    return code, json.loads(lines[0])


def test_ready_reports_packages():
    code, doc = _run(
        {"protocol": PROTOCOL_VERSION, "command": "ready", "payload": {}, "limits": {}}
    )
    assert code == 0
    assert doc["ok"] is True
    result = doc["result"]
    assert set(result["packages"]) == {"skrf", "numpy", "scipy", "matplotlib"}
    assert result["ready"] is True
    assert result["python"]["version"]


def test_rejects_invalid_json():
    code, doc = _run("{not json")
    assert code == 2
    assert doc["ok"] is False
    assert doc["error"]["code"] == "bad_request"


def test_rejects_protocol_mismatch():
    code, doc = _run({"protocol": 999, "command": "ready", "payload": {}, "limits": {}})
    assert code == 2
    assert doc["error"]["code"] == "bad_request"
    assert "protocol mismatch" in doc["error"]["message"]


def test_rejects_unknown_command():
    code, doc = _run(
        {"protocol": PROTOCOL_VERSION, "command": "explode", "payload": {}, "limits": {}}
    )
    assert code == 2
    assert doc["error"]["code"] == "unsupported_command"


def test_memory_limit_does_not_break_ready():
    code, doc = _run(
        {
            "protocol": PROTOCOL_VERSION,
            "command": "ready",
            "payload": {},
            "limits": {"max_memory_mb": 4096},
        }
    )
    assert code == 0 and doc["ok"] is True
