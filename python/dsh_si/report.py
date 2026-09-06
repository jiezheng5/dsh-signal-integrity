"""Report directory layout and writers: PNG plots, CSV data, results.json, HTML.

Every report is one directory:
    <output_dir>/<stem>-<hash8>-<UTC timestamp>/
        results.json   machine-readable: input hash, versions, settings, warnings, summary
        *.png          plots (also embedded in the HTML)
        *.csv          per-frequency data
        report.html    self-contained summary
"""

from __future__ import annotations

import base64
import csv
import json
import platform
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from . import __version__
from .protocol import WorkerError

SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


def versions() -> dict[str, str]:
    import matplotlib
    import numpy
    import scipy
    import skrf

    return {
        "dsh_si": __version__,
        "python": platform.python_version(),
        "scikit-rf": skrf.__version__,
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
    }


def create_report_dir(
    output_dir: str | Path, stem: str, file_hash: str, kind: str = "analyze"
) -> Path:
    safe = SAFE_STEM.sub("_", stem).strip("_") or "report"
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Path(output_dir).expanduser() / kind / f"{safe}-{file_hash[:8]}-{stamp}"
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        root = (
            Path(output_dir).expanduser()
            / kind
            / f"{safe}-{file_hash[:8]}-{stamp}-{datetime.now(UTC).microsecond:06d}"
        )
        root.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise WorkerError(
            "report_write_failed", f"cannot create report directory under {output_dir}: {exc}"
        ) from exc
    return root


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    try:
        path.write_text(
            json.dumps(payload, indent=2, allow_nan=False, default=_json_default) + "\n"
        )
    except (OSError, ValueError) as exc:
        raise WorkerError("report_write_failed", f"cannot write {path.name}: {exc}") from exc
    return path


def _json_default(value: Any) -> Any:
    import numpy as np

    if isinstance(value, np.generic):
        out = value.item()
        if isinstance(out, float) and out != out:  # NaN
            return None
        return out
    if isinstance(value, np.ndarray):
        return [None if (isinstance(v, float) and v != v) else v for v in value.tolist()]
    if isinstance(value, complex):
        return {"re": value.real, "im": value.imag}
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_csv(path: Path, header: list[str], rows: Any) -> Path:
    try:
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in rows:
                writer.writerow(["" if (isinstance(v, float) and v != v) else v for v in row])
    except OSError as exc:
        raise WorkerError("report_write_failed", f"cannot write {path.name}: {exc}") from exc
    return path


def write_html(path: Path, title: str, sections: list[dict[str, Any]]) -> Path:
    """sections: [{heading, text?, image? (png path), table? {header, rows}, links? [paths]}]"""
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{escape(title)}</title>",
        "<style>body{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1a1a1a}",
        "h1{font-size:22px}h2{font-size:17px;margin-top:28px;border-top:1px solid #e3e3e3;padding-top:8px}",
        "img{max-width:100%;border:1px solid #e3e3e3;border-radius:6px}table{border-collapse:collapse;font-size:14px}",
        "td,th{border-bottom:1px solid #e3e3e3;padding:5px 9px;text-align:left}pre{background:#f3f4f6;padding:10px;overflow:auto}</style>",
        f"</head><body><h1>{escape(title)}</h1>",
    ]
    for section in sections:
        parts.append(f"<h2>{escape(str(section.get('heading', '')))}</h2>")
        if section.get("text"):
            parts.append(f"<p>{escape(str(section['text']))}</p>")
        if section.get("pre"):
            parts.append(f"<pre>{escape(str(section['pre']))}</pre>")
        image = section.get("image")
        if image is not None:
            data = base64.b64encode(Path(image).read_bytes()).decode("ascii")
            parts.append(
                f"<img alt='{escape(Path(image).stem)}' src='data:image/png;base64,{data}'>"
            )
        table = section.get("table")
        if table:
            parts.append(
                "<table><tr>"
                + "".join(f"<th>{escape(str(h))}</th>" for h in table["header"])
                + "</tr>"
            )
            for row in table["rows"]:
                parts.append("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in row) + "</tr>")
            parts.append("</table>")
        links = section.get("links") or []
        if links:
            parts.append(
                "<p>"
                + " · ".join(
                    f"<a href='{escape(Path(p).name)}'>{escape(Path(p).name)}</a>" for p in links
                )
                + "</p>"
            )
    parts.append("</body></html>")
    try:
        path.write_text("\n".join(parts))
    except OSError as exc:
        raise WorkerError("report_write_failed", f"cannot write {path.name}: {exc}") from exc
    return path
