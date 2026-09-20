#!/usr/bin/env python3
"""Generate a README SVG from GitHub's anonymous contribution calendar.

Uses only public profile data, without a token or cookies. Public counts may
include anonymized private contributions if the profile owner has enabled them.
The output is replaced atomically only after all 31 UTC calendar days validate.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


WINDOW_DAYS = 31
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
COUNT_PATTERN = re.compile(r"^(No|[0-9][0-9,]*) contributions? on .+\.$")


class ContributionParser(HTMLParser):
    """Join calendar cells to their exact counts by the tooltip's `for` ID."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.dates: dict[str, date] = {}
        self.counts: dict[str, int] = {}
        self._tooltip_id: str | None = None
        self._tooltip_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "td" and "ContributionCalendar-day" in classes:
            cell_id = attributes.get("id")
            day = attributes.get("data-date")
            if not cell_id or not day or cell_id in self.dates:
                raise ValueError("Calendar contains a missing or duplicate day ID/date")
            self.dates[cell_id] = date.fromisoformat(day)
        if tag == "tool-tip":
            if self._tooltip_id is not None:
                raise ValueError("Unexpected nested contribution tooltip")
            self._tooltip_id = attributes.get("for")
            self._tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_id is not None:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip" or self._tooltip_id is None:
            return
        target = self._tooltip_id
        label = " ".join("".join(self._tooltip_text).split())
        match = COUNT_PATTERN.fullmatch(label)
        if match:
            if target in self.counts:
                raise ValueError("Calendar contains a duplicate contribution tooltip")
            self.counts[target] = (
                0 if match.group(1) == "No" else int(match.group(1).replace(",", ""))
            )
        self._tooltip_id = None
        self._tooltip_text = []


def parse_contributions(html: str, today: date) -> list[tuple[date, int]]:
    parser = ContributionParser()
    parser.feed(html)
    parser.close()
    calendar: dict[date, int] = {}
    for cell_id, day in parser.dates.items():
        if cell_id not in parser.counts:
            raise ValueError(f"Missing or unrecognized contribution count for {day}")
        if day in calendar:
            raise ValueError(f"Duplicate contribution date: {day}")
        calendar[day] = parser.counts[cell_id]
    days = [today - timedelta(days=offset) for offset in range(WINDOW_DAYS - 1, -1, -1)]
    missing = [day.isoformat() for day in days if day not in calendar]
    if missing:
        raise ValueError("Public calendar is missing dates: " + ", ".join(missing))
    return [(day, calendar[day]) for day in days]


def fetch_contributions(username: str, today: date) -> list[tuple[date, int]]:
    # Do not use authenticated API clients: the README must reflect public data.
    request = Request(
        f"https://github.com/users/{username}/contributions",
        headers={
            "User-Agent": "github-profile-activity-graph",
            "Accept": "text/html",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urlopen(request, timeout=30) as response:
        if response.status != 200 or response.headers.get_content_type() != "text/html":
            raise ValueError("GitHub did not return a successful HTML contribution calendar")
        html = response.read().decode("utf-8")
    return parse_contributions(html, today)


def render_svg(username: str, daily: list[tuple[date, int]]) -> str:
    width, height = 1000, 330
    left, right, top, bottom = 65, 972, 102, 264
    plot_width, plot_height = right - left, bottom - top
    peak = max(count for _, count in daily)
    raw_step = max(peak, 1) / 4
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = next(value * magnitude for value in (1, 2, 5, 10) if value * magnitude >= raw_step)
    step = max(1, int(step))
    ceiling = math.ceil(max(peak, 1) / step) * step
    points = [
        (left + index * plot_width / (len(daily) - 1), bottom - count * plot_height / ceiling)
        for index, (_, count) in enumerate(daily)
    ]
    line = " ".join(f"{'M' if index == 0 else 'L'} {x:.2f} {y:.2f}" for index, (x, y) in enumerate(points))
    area = f"{line} L {right} {bottom} L {left} {bottom} Z"
    first_day, last_day = daily[0][0].isoformat(), daily[-1][0].isoformat()
    total = sum(count for _, count in daily)
    title = f"{username}'s contribution activity"
    description = (
        f"Daily contributions visible on the public GitHub profile from {first_day} to {last_day} UTC. "
        f"{total:,} contributions across {len(daily)} days. Today's count is partial. "
        + "; ".join(f"{day.isoformat()}: {count}" for day, count in daily)
        + "."
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="activity-title activity-description">',
        f'<title id="activity-title">{escape(title)}</title>',
        f'<desc id="activity-description">{escape(description)}</desc>',
        f'<rect width="{width}" height="{height}" rx="8" fill="#0D1117"/>',
        '<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" fill="#ffffff">',
        '<text x="30" y="35" font-size="20" font-weight="600">Contribution activity</text>',
        f'<text x="30" y="60" font-size="13" fill="#b1bac4">{first_day} – {last_day} · Last 31 days · UTC</text>',
        f'<text x="970" y="35" font-size="16" font-weight="600" text-anchor="end">{total:,} contributions</text>',
        '<text x="65" y="87" font-size="11" fill="#b1bac4">Contributions / day</text>',
    ]
    for value in range(0, ceiling + 1, step):
        y = bottom - value * plot_height / ceiling
        parts.extend([
            f'<path d="M {left} {y:.2f} H {right}" stroke="#30363d" stroke-width="1"/>',
            f'<text x="53" y="{y + 4:.2f}" font-size="11" fill="#b1bac4" text-anchor="end">{value}</text>',
        ])
    parts.extend([
        f'<path d="{area}" fill="#ffffff" fill-opacity="0.10"/>',
        f'<path d="{line}" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>',
    ])
    for (day, count), (x, y) in zip(daily, points):
        parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="3" fill="#ffffff"><title>{day.isoformat()}: {count} contributions</title></circle>')
    for index in (0, 5, 10, 15, 20, 25, 30):
        day = daily[index][0]
        x = points[index][0]
        parts.extend([
            f'<path d="M {x:.2f} {bottom} v 5" stroke="#8b949e"/>',
            f'<text x="{x:.2f}" y="284" font-size="11" fill="#b1bac4" text-anchor="middle">{day.strftime("%b")} {day.day}</text>',
        ])
    parts.extend([
        '<text x="30" y="315" font-size="11" fill="#8b949e">Public GitHub profile · Today is partial</text>',
        '</g>',
        '</svg>',
    ])
    return "\n".join(parts) + "\n"


def write_atomic(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix=f".{output.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="TaewoooPark")
    parser.add_argument("--output", type=Path, default=Path("assets/activity-graph.svg"))
    args = parser.parse_args()
    if not USERNAME_PATTERN.fullmatch(args.username):
        parser.error("username must be a GitHub username containing letters, digits, or hyphens")
    try:
        today = datetime.now(timezone.utc).date()
        daily = fetch_contributions(args.username, today)
        svg = render_svg(args.username, daily)
        write_atomic(args.output, svg)
    except (OSError, URLError, ValueError) as error:
        print(f"Cannot update activity graph: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}: {daily[0][0]} to {daily[-1][0]}, {sum(count for _, count in daily):,} public-profile contributions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
