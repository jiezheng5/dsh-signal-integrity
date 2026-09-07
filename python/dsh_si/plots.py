"""Matplotlib figures for reports and inline chat images.

Rules kept deliberately small: one axis per figure, a fixed categorical
palette assigned in order (never cycled past eight series), thin lines, a
legend whenever more than one series is drawn, recessive grid, units in every
axis label, and the extraction assumptions in the subtitle.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

PALETTE = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
MAX_SERIES = len(PALETTE)
DB_FLOOR = -120.0


def db(values: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(values), 10 ** (DB_FLOOR / 20)))


def overview_terms(network: Any, max_terms: int = MAX_SERIES) -> list[tuple[int, int]]:
    """Which S_ij to draw: reflections first (up to 4), then the strongest transmissions.

    Returns 0-based (i, j) index pairs, at most `max_terms`.
    """
    n = int(network.nports)
    s = np.asarray(network.s)
    terms: list[tuple[int, int]] = [(i, i) for i in range(min(n, 4))]
    if n > 1:
        strength = {
            (i, j): float(np.mean(np.abs(s[:, i, j]))) for i in range(n) for j in range(n) if i != j
        }
        for pair in sorted(strength, key=lambda p: -strength[p]):
            if len(terms) >= max_terms:
                break
            terms.append(pair)
    return terms[:max_terms]


def s_magnitude_overview(
    network: Any, title: str, subtitle: str, terms: list[tuple[int, int]] | None = None
) -> Any:
    """|S_ij| in dB versus frequency for the selected terms."""
    terms = terms if terms is not None else overview_terms(network)
    f_ghz = np.asarray(network.frequency.f, dtype=float) / 1e9
    s = np.asarray(network.s)
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100)
    for k, (i, j) in enumerate(terms):
        ax.plot(
            f_ghz,
            db(s[:, i, j]),
            color=PALETTE[k % MAX_SERIES],
            linewidth=1.6,
            label=f"S{i + 1}{j + 1}",
        )
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("|S| (dB)")
    ax.set_title(f"{title}\n{subtitle}", fontsize=11, loc="left")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if len(terms) > 1:
        ax.legend(frameon=False, ncol=2 if len(terms) > 4 else 1, fontsize=9)
    total = int(network.nports) ** 2
    if len(terms) < total:
        ax.text(
            1.0,
            -0.14,
            f"showing {len(terms)} of {total} terms",
            transform=ax.transAxes,
            ha="right",
            fontsize=8,
            color="#52514e",
        )
    fig.tight_layout()
    return fig


REGION_SHADE = {
    "near_srf": "#eda100",
    "beyond_srf": "#e34948",
    "wrong_sign": "#e34948",
    "dc": "#52514e",
}


def lumped_quantity(
    freq_hz: np.ndarray,
    values: np.ndarray,
    regions: list[str],
    srf_hz: float | None,
    ylabel: str,
    scale: float,
    title: str,
    subtitle: str,
) -> Any:
    """One extracted quantity versus frequency; points outside the valid region are shaded.

    `scale` converts SI values to the display unit named in `ylabel` (1e9 for nH, 1e12 for pF).
    Invalid points stay on the curve (the reader should see the shape) but the band is shaded
    and the self-resonance is marked, so the plot never presents a wrong-sign or beyond-SRF
    value as a component parameter.
    """
    f_ghz = np.asarray(freq_hz, dtype=float) / 1e9
    y = np.asarray(values, dtype=float) * scale
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100)
    ax.plot(f_ghz, y, color=PALETTE[0], linewidth=1.6, label=ylabel.split(" (")[0])
    shaded: set[str] = set()
    start = None
    for k, label in enumerate(list(regions) + [None]):
        if label not in REGION_SHADE and start is not None:
            lo, hi = f_ghz[start], f_ghz[k - 1]
            ax.axvspan(lo, hi, color=REGION_SHADE[regions[start]], alpha=0.12, linewidth=0)
            shaded.add(regions[start])
            start = None
        if label in REGION_SHADE and (start is None or regions[start] != label):
            if start is not None:
                ax.axvspan(
                    f_ghz[start],
                    f_ghz[k - 1],
                    color=REGION_SHADE[regions[start]],
                    alpha=0.12,
                    linewidth=0,
                )
                shaded.add(regions[start])
            start = k
    if srf_hz is not None:
        ax.axvline(
            srf_hz / 1e9,
            color="#52514e",
            linewidth=0.9,
            linestyle="--",
            label=f"SRF {srf_hz / 1e9:.3g} GHz",
        )
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n{subtitle}", fontsize=11, loc="left")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if srf_hz is not None or shaded:
        ax.legend(frameon=False, fontsize=9)
    if shaded:
        ax.text(
            1.0,
            -0.14,
            "shaded: " + ", ".join(sorted(shaded)).replace("_", " "),
            transform=ax.transAxes,
            ha="right",
            fontsize=8,
            color="#52514e",
        )
    fig.tight_layout()
    return fig


def save_png(fig: Any, path: Path, dpi: int = 130) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    return path
