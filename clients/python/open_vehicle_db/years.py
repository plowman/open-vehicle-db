"""
Compressed year-range encoding: (2018, 2020, 2021, 2022) <-> "2018,2020-2022".

Model years are stored this way so that each CSV row is one real-world thing — a model, a style —
rather than one row per year. It keeps "this style now also comes in 2027" to a single changed line
in a diff instead of an insertion buried in a run of near-identical rows.
"""

from __future__ import annotations

from collections.abc import Iterable


def format_years(years: Iterable[int]) -> str:
    """Collapse years into ascending comma-separated ranges. Duplicates and disorder are fine."""
    ordered = sorted(set(years))
    if not ordered:
        return ""

    runs = []
    start = end = ordered[0]
    for year in ordered[1:]:
        if year == end + 1:
            end = year
            continue
        runs.append((start, end))
        start = end = year
    runs.append((start, end))

    return ",".join(str(first) if first == last else f"{first}-{last}" for first, last in runs)


def parse_years(encoded: str) -> tuple[int, ...]:
    """Expand what format_years wrote back into an ascending tuple with no duplicates."""
    encoded = (encoded or "").strip()
    if not encoded:
        return ()

    years: list[int] = []
    for group in encoded.split(","):
        group = group.strip()
        if not group:
            continue
        first_text, _, last_text = group.partition("-")
        first = int(first_text)
        last = int(last_text) if last_text else first
        if last < first:
            raise ValueError(f"Year range {group!r} ends before it starts")
        years.extend(range(first, last + 1))

    return tuple(sorted(set(years)))
