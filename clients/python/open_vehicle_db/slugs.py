"""
Slugs are the stable keys that tie the CSVs together, so both the updater and the client build them
the same way from this one place.
"""

from __future__ import annotations

import re

_NOT_SLUG_CHARACTER = re.compile("[^a-z0-9_]")


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = slug.replace(" ", "_").replace("-", "_")
    return _NOT_SLUG_CHARACTER.sub("", slug)
