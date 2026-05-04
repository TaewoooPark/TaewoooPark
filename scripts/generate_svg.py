#!/usr/bin/env python3
"""
Render a Claude Code usage widget SVG from ccusage --json output.

Usage:
    python generate_svg.py <usage.json> <out.svg>

The SVG is pure SMIL (no <script>) so it renders animated on GitHub README.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


# ---------- layout constants ----------

VIEW_W = 1000
VIEW_H = 300

LP_CENTER_X = 210          # left panel text center
RP_X = 420                 # right panel (chart) x
RP_Y = 50                  # chart top
RP_W = 540                 # chart width
RP_H = 210                 # chart height

WINDOW_DAYS = 60           # rolling window anchored at latest data point

FRAMES = 36                # count-up keyframes
COUNT_DUR = 1.6            # count-up animation duration (s)
CHART_DUR = 1.8            # chart draw animation duration (s)
CHART_DELAY = 0.2

BG = "#0D1117"
FG = "#FFFFFF"
MUTED = "#8B949E"

FONT = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace'


# ---------- helpers ----------

def ease_out_expo(t: float) -> float:
    if t >= 1.0:
        return 1.0
    if t <= 0.0:
        return 0.0
    return 1.0 - pow(2.0, -10.0 * t)


def catmull_rom_path(points: list[tuple[float, float]]) -> str:
    """Centripetal-ish Catmull-Rom spline rendered as cubic Beziers."""
    if not points:
        return ""
    if len(points) == 1:
        x, y = points[0]
        return f"M {x:.2f} {y:.2f}"

    d = [f"M {points[0][0]:.2f} {points[0][1]:.2f}"]
    n = len(points)
    for i in range(n - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i + 2 < n else p2

        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0

        d.append(
            f"C {c1x:.2f} {c1y:.2f} {c2x:.2f} {c2y:.2f} "
            f"{p2[0]:.2f} {p2[1]:.2f}"
        )
    return " ".join(d)


def active_day_count(daily: list[dict]) -> int:
    return len([d for d in daily if d.get("totalTokens", 0) > 0])


_DATE_FORMATS = ("%Y-%m-%d", "%b %d, %Y")


def parse_date(s: str) -> datetime:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"unrecognized date format: {s!r}")


def window_filter(daily: list[dict], window_days: int) -> list[dict]:
    """Keep the most recent `window_days` active-day entries."""
    if not daily:
        return []
    return sorted(daily, key=lambda d: parse_date(d["date"]))[-window_days:]


def cumulative_series(daily: list[dict]) -> list[tuple[str, int]]:
    cum = 0
    out: list[tuple[str, int]] = []
    for d in sorted(daily, key=lambda x: parse_date(x["date"])):
        cum += int(d.get("totalTokens", 0))
        out.append((d["date"], cum))
    return out


# ---------- rendering ----------

def build_count_up(total: int) -> str:
    step = COUNT_DUR / FRAMES
    parts: list[str] = []
    for i in range(FRAMES):
        t = (i + 1) / FRAMES
        value = int(round(ease_out_expo(t) * total))
        begin = i * step
        end = (i + 1) * step

        sets = [
            f'<set attributeName="opacity" to="1" '
            f'begin="{begin:.3f}s" fill="freeze"/>'
        ]
        if i < FRAMES - 1:
            sets.append(
                f'<set attributeName="opacity" to="0" '
                f'begin="{end:.3f}s" fill="freeze"/>'
            )

        parts.append(
            f'<text x="{LP_CENTER_X}" y="160" text-anchor="middle" '
            f'font-family=\'{FONT}\' font-size="46" font-weight="700" '
            f'fill="{FG}" opacity="0" '
            f'letter-spacing="-0.01em">'
            f"{value:,}"
            + "".join(sets)
            + "</text>"
        )
    return "\n    ".join(parts)


def build_chart(points: list[tuple[float, float]]) -> tuple[str, str, tuple[float, float]]:
    line_d = catmull_rom_path(points)
    last_x, last_y = points[-1]
    area_d = (
        line_d
        + f" L {last_x:.2f} {RP_Y + RP_H:.2f} "
        + f"L {RP_X:.2f} {RP_Y + RP_H:.2f} Z"
    )
    return line_d, area_d, (last_x, last_y)


def render(data: dict) -> str:
    daily = window_filter(data["daily"], WINDOW_DAYS)

    total_tokens = sum(int(d.get("totalTokens", 0)) for d in daily)
    days = active_day_count(daily)

    cum = cumulative_series(daily)
    max_cum = max(v for _, v in cum) or 1
    n = len(cum)

    points: list[tuple[float, float]] = []
    for i, (_, v) in enumerate(cum):
        x = RP_X + (i / max(n - 1, 1)) * RP_W
        # a tiny 4px top padding so the peak dot isn't clipped
        y = RP_Y + 4 + (RP_H - 4) - (v / max_cum) * (RP_H - 4)
        points.append((x, y))

    line_d, area_d, (peak_x, peak_y) = build_chart(points)
    count_up = build_count_up(total_tokens)

    label_appear_begin = 0.05
    caption_begin = COUNT_DUR - 0.15
    dot_begin = CHART_DELAY + CHART_DUR - 0.1
    peak_value_str = f"{total_tokens:,}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" width="{VIEW_W}" height="{VIEW_H}" shape-rendering="geometricPrecision" text-rendering="optimizeLegibility" font-rendering="optimizeLegibility">
  <defs>
    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%"  stop-color="{FG}" stop-opacity="0.38"/>
      <stop offset="60%" stop-color="{FG}" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="{BG}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="chartReveal">
      <rect x="{RP_X}" y="0" width="0" height="{VIEW_H}">
        <animate attributeName="width" from="0" to="{RP_W + 20}"
                 begin="{CHART_DELAY}s" dur="{CHART_DUR}s" fill="freeze"/>
      </rect>
    </clipPath>
  </defs>

  <!-- background -->
  <rect width="{VIEW_W}" height="{VIEW_H}" fill="{BG}"/>

  <!-- left: small label -->
  <text x="{LP_CENTER_X}" y="95" text-anchor="middle"
        font-family='{FONT}' font-size="10.5" font-weight="500"
        fill="{MUTED}" letter-spacing="2.4" opacity="0">
    TOKENS PROCESSED · LAST {WINDOW_DAYS} DAYS
    <animate attributeName="opacity" from="0" to="1"
             begin="{label_appear_begin}s" dur="0.5s" fill="freeze"/>
  </text>

  <!-- left: count-up frames -->
  <g>
    {count_up}
  </g>

  <!-- left: caption -->
  <text x="{LP_CENTER_X}" y="212" text-anchor="middle"
        font-family='{FONT}' font-size="13" font-weight="400"
        fill="{MUTED}" letter-spacing="0.02em" opacity="0">
    {days} days. One developer.
    <animate attributeName="opacity" from="0" to="1"
             begin="{caption_begin:.2f}s" dur="0.5s" fill="freeze"/>
  </text>

  <!-- right: chart -->
  <g clip-path="url(#chartReveal)">
    <path d="{area_d}" fill="url(#areaGrad)"/>
    <path d="{line_d}" fill="none" stroke="{FG}"
          stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </g>

  <!-- right: baseline hairline -->
  <line x1="{RP_X}" y1="{RP_Y + RP_H}" x2="{RP_X + RP_W}" y2="{RP_Y + RP_H}"
        stroke="{MUTED}" stroke-opacity="0.25" stroke-width="0.5"/>

  <!-- right: peak annotation -->
  <circle cx="{peak_x:.2f}" cy="{peak_y:.2f}" r="0" fill="{FG}">
    <animate attributeName="r" from="0" to="3.5"
             begin="{dot_begin:.2f}s" dur="0.35s" fill="freeze"/>
  </circle>
  <text x="{peak_x - 8:.2f}" y="{peak_y - 10:.2f}" text-anchor="end"
        font-family='{FONT}' font-size="10" font-weight="500"
        fill="{FG}" opacity="0">
    {peak_value_str}
    <animate attributeName="opacity" from="0" to="0.85"
             begin="{dot_begin + 0.2:.2f}s" dur="0.4s" fill="freeze"/>
  </text>
</svg>
"""


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: generate_svg.py <usage.json> <out.svg>", file=sys.stderr)
        return 2

    src = Path(argv[1])
    dst = Path(argv[2])

    data = json.loads(src.read_text())
    svg = render(data)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(svg)
    print(f"wrote {dst} ({len(svg):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
