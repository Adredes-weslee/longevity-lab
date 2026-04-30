"""Small dependency-free figure writers for scripted reports."""

from __future__ import annotations

import html
import struct
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BarDatum:
    """One bar in a simple report chart."""

    label: str
    value: float


PALETTE: tuple[str, ...] = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#F0E442",
    "#56B4E9",
    "#E69F00",
)
PNG_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 114, 178),
    (213, 94, 0),
    (0, 158, 115),
    (204, 121, 167),
    (240, 228, 66),
    (86, 180, 233),
    (230, 159, 0),
)


def _max_value(data: Sequence[BarDatum]) -> float:
    """Return a non-zero maximum scale value for chart rendering."""
    if not data:
        return 1.0
    return max(1.0, max(abs(item.value) for item in data))


def write_bar_chart_svg(
    path: Path,
    data: Sequence[BarDatum],
    *,
    title: str,
    y_axis_label: str,
    value_suffix: str = "",
    width: int = 800,
    height: int = 420,
) -> None:
    """Write a labeled SVG bar chart."""
    margin_left = 88
    margin_right = 32
    margin_top = 56
    margin_bottom = 108
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    max_value = _max_value(data)
    bar_gap = 12
    bar_slot = chart_width / max(1, len(data))
    bar_width = max(10.0, bar_slot - bar_gap)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{html.escape(title)}</title>',
        f'<desc id="desc">{html.escape(y_axis_label)} bar chart.</desc>',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{margin_left}" y="30" font-family="Arial, sans-serif" '
        f'font-size="20" font-weight="700" fill="#111827">{html.escape(title)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + chart_height}" '
        f'x2="{margin_left + chart_width}" y2="{margin_top + chart_height}" '
        'stroke="#374151" stroke-width="1"/>',
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" '
        f'y2="{margin_top + chart_height}" stroke="#374151" stroke-width="1"/>',
        f'<text x="18" y="{margin_top + chart_height / 2}" '
        'font-family="Arial, sans-serif" font-size="12" fill="#374151" '
        f'transform="rotate(-90 18 {margin_top + chart_height / 2})">'
        f"{html.escape(y_axis_label)}</text>",
    ]

    for index, item in enumerate(data):
        value = max(0.0, item.value)
        bar_height = (value / max_value) * chart_height
        x = margin_left + index * bar_slot + (bar_slot - bar_width) / 2
        y = margin_top + chart_height - bar_height
        color = PALETTE[index % len(PALETTE)]
        label = html.escape(item.label)
        value_label = f"{value:.1f}{value_suffix}"
        parts.extend(
            [
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                f'height="{bar_height:.1f}" fill="{color}"/>',
                f'<text x="{x + bar_width / 2:.1f}" y="{y - 6:.1f}" '
                'font-family="Arial, sans-serif" font-size="12" fill="#111827" '
                f'text-anchor="middle">{html.escape(value_label)}</text>',
                f'<text x="{x + bar_width / 2:.1f}" y="{margin_top + chart_height + 20}" '
                'font-family="Arial, sans-serif" font-size="11" fill="#374151" '
                f'text-anchor="end" transform="rotate(-35 {x + bar_width / 2:.1f} '
                f'{margin_top + chart_height + 20})">{label}</text>',
            ]
        )

    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    """Return one PNG chunk."""
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(payload, checksum)
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)


def _fill_rect(
    pixels: bytearray,
    *,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    """Fill an axis-aligned rectangle in an RGB buffer."""
    left = max(0, min(width, x0))
    right = max(0, min(width, x1))
    top = max(0, min(height, y0))
    bottom = max(0, min(height, y1))
    if left >= right or top >= bottom:
        return
    red, green, blue = color
    for y in range(top, bottom):
        row_start = y * width * 3
        for x in range(left, right):
            index = row_start + x * 3
            pixels[index] = red
            pixels[index + 1] = green
            pixels[index + 2] = blue


def write_bar_chart_png(
    path: Path,
    data: Sequence[BarDatum],
    *,
    width: int = 800,
    height: int = 420,
) -> None:
    """Write a simple RGB PNG bar chart."""
    pixels = bytearray([255] * width * height * 3)
    margin_left = 88
    margin_right = 32
    margin_top = 56
    margin_bottom = 88
    chart_width = width - margin_left - margin_right
    chart_height = height - margin_top - margin_bottom
    baseline = margin_top + chart_height
    max_value = _max_value(data)

    _fill_rect(
        pixels,
        width=width,
        height=height,
        x0=margin_left,
        y0=margin_top,
        x1=margin_left + 1,
        y1=baseline,
        color=(55, 65, 81),
    )
    _fill_rect(
        pixels,
        width=width,
        height=height,
        x0=margin_left,
        y0=baseline,
        x1=margin_left + chart_width,
        y1=baseline + 1,
        color=(55, 65, 81),
    )

    if data:
        bar_gap = 12
        bar_slot = chart_width / len(data)
        bar_width = max(10, int(bar_slot - bar_gap))
        for index, item in enumerate(data):
            value = max(0.0, item.value)
            bar_height = int((value / max_value) * chart_height)
            x = int(margin_left + index * bar_slot + (bar_slot - bar_width) / 2)
            y = baseline - bar_height
            _fill_rect(
                pixels,
                width=width,
                height=height,
                x0=x,
                y0=y,
                x1=x + bar_width,
                y1=baseline,
                color=PNG_PALETTE[index % len(PNG_PALETTE)],
            )

    rows = []
    for y in range(height):
        start = y * width * 3
        rows.append(b"\x00" + bytes(pixels[start : start + width * 3]))
    raw = b"".join(rows)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
