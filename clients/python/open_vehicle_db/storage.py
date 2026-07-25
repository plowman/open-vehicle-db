"""
Reading and writing the files in data/.

This is the only module that knows what is on disk or in what format. Callers hand it dataclasses and
get dataclasses back. CSV rows are always written sorted by their natural key with a plain "\\n" line
ending, so that a run which changes one style produces a one line diff on any platform.
"""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .models import Make, Model, OrphanedStyle, Style, VehicleDatabase, VehicleType
from .years import format_years, parse_years

# clients/python/open_vehicle_db/storage.py -> the repo root is four levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]

# The data is read relative to the checkout. The environment variable is here for tests and for
# anyone vendoring the CSVs somewhere else.
DATA_DIR = Path(os.environ.get("OPEN_VEHICLE_DB_DATA") or REPO_ROOT / "data")

STATS_JSON = "stats.json"

MAKES_CSV = "makes.csv"
MODELS_CSV = "models.csv"
STYLES_CSV = "styles.csv"
ORPHANED_STYLES_CSV = "orphaned_styles.csv"

MAKE_COLUMNS = ["make_slug", "make_id", "make_name", "first_year", "last_year"]
MODEL_COLUMNS = ["make_slug", "model_slug", "model_name", "model_id", "vehicle_type", "years"]
STYLE_COLUMNS = ["make_slug", "model_slug", "style_name", "years"]
ORPHANED_STYLE_COLUMNS = ["make_slug", "style_name", "occurrences"]


def data_path(filename: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / filename


def _read_rows(filename: str, data_dir: Path | None = None) -> Iterable[dict[str, str]]:
    path = data_path(filename, data_dir)
    with open(path, newline="", encoding="utf-8") as csv_file:
        yield from csv.DictReader(csv_file)


def _write_rows(filename: str, columns: list[str], rows: Iterable[dict], data_dir: Path | None = None) -> None:
    path = data_path(filename, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _optional_int(value: str) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def read_makes(data_dir: Path | None = None) -> tuple[Make, ...]:
    return tuple(
        Make(
            make_slug=row["make_slug"],
            make_id=int(row["make_id"]),
            make_name=row["make_name"],
            first_year=_optional_int(row["first_year"]),
            last_year=_optional_int(row["last_year"]),
        )
        for row in _read_rows(MAKES_CSV, data_dir)
    )


def write_makes(makes: Iterable[Make], data_dir: Path | None = None) -> None:
    _write_rows(
        MAKES_CSV,
        MAKE_COLUMNS,
        (
            {
                "make_slug": make.make_slug,
                "make_id": make.make_id,
                "make_name": make.make_name,
                "first_year": "" if make.first_year is None else make.first_year,
                "last_year": "" if make.last_year is None else make.last_year,
            }
            for make in sorted(makes)
        ),
        data_dir,
    )


def read_models(data_dir: Path | None = None) -> tuple[Model, ...]:
    return tuple(
        Model(
            make_slug=row["make_slug"],
            model_slug=row["model_slug"],
            model_name=row["model_name"],
            model_id=int(row["model_id"]),
            vehicle_type=VehicleType(row["vehicle_type"]),
            years=parse_years(row["years"]),
        )
        for row in _read_rows(MODELS_CSV, data_dir)
    )


def write_models(models: Iterable[Model], data_dir: Path | None = None) -> None:
    _write_rows(
        MODELS_CSV,
        MODEL_COLUMNS,
        (
            {
                "make_slug": model.make_slug,
                "model_slug": model.model_slug,
                "model_name": model.model_name,
                "model_id": model.model_id,
                "vehicle_type": model.vehicle_type.value,
                "years": format_years(model.years),
            }
            for model in sorted(models)
        ),
        data_dir,
    )


def read_styles(data_dir: Path | None = None) -> tuple[Style, ...]:
    return tuple(
        Style(
            make_slug=row["make_slug"],
            model_slug=row["model_slug"],
            style_name=row["style_name"],
            years=parse_years(row["years"]),
        )
        for row in _read_rows(STYLES_CSV, data_dir)
    )


def write_styles(styles: Iterable[Style], data_dir: Path | None = None) -> None:
    _write_rows(
        STYLES_CSV,
        STYLE_COLUMNS,
        (
            {
                "make_slug": style.make_slug,
                "model_slug": style.model_slug,
                "style_name": style.style_name,
                "years": format_years(style.years),
            }
            for style in sorted(styles)
        ),
        data_dir,
    )


def read_orphaned_styles(data_dir: Path | None = None) -> tuple[OrphanedStyle, ...]:
    return tuple(
        OrphanedStyle(
            make_slug=row["make_slug"],
            style_name=row["style_name"],
            occurrences=int(row["occurrences"]),
        )
        for row in _read_rows(ORPHANED_STYLES_CSV, data_dir)
    )


def write_orphaned_styles(orphaned_styles: Iterable[OrphanedStyle], data_dir: Path | None = None) -> None:
    _write_rows(
        ORPHANED_STYLES_CSV,
        ORPHANED_STYLE_COLUMNS,
        (
            {
                "make_slug": orphan.make_slug,
                "style_name": orphan.style_name,
                "occurrences": orphan.occurrences,
            }
            for orphan in sorted(orphaned_styles)
        ),
        data_dir,
    )


def load_database(data_dir: Path | None = None, missing_ok: bool = False) -> VehicleDatabase:
    """
    Read the whole dataset.

    missing_ok is for the updater, which has to cope with a checkout that has no CSVs yet. The client
    leaves it off so that a wrong data directory is an error rather than a silently empty database.
    """

    def read(reader, filename):
        if missing_ok and not data_path(filename, data_dir).exists():
            return ()
        return reader(data_dir)

    return VehicleDatabase(
        makes=read(read_makes, MAKES_CSV),
        models=read(read_models, MODELS_CSV),
        styles=read(read_styles, STYLES_CSV),
    )


def write_database(database: VehicleDatabase, data_dir: Path | None = None) -> None:
    write_makes(database.makes, data_dir)
    write_models(database.models, data_dir)
    write_styles(database.styles, data_dir)


CHANGELOG_MARKDOWN = "CHANGELOG.md"

CHANGELOG_HEADER = """# Data changelog

What each update run changed, newest first. Generated by `scripts/update_car_data.py`; the CSVs in
this directory are the actual data.
"""


def prepend_changelog(section: str, data_dir: Path | None = None) -> None:
    """
    Put a new section directly under the header, so the newest run is the first thing you read.

    Rewriting the whole file rather than appending keeps the reading order right. The file is small
    enough that this costs nothing.
    """
    path = data_path(CHANGELOG_MARKDOWN, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing_sections = ""
    if path.exists():
        contents = path.read_text(encoding="utf-8")
        _, marker, remainder = contents.partition("\n## ")
        existing_sections = (marker + remainder).lstrip("\n") if marker else ""

    body = f"{CHANGELOG_HEADER}\n{section.rstrip()}\n"
    if existing_sections:
        body += f"\n{existing_sections.rstrip()}\n"

    path.write_text(body, encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Stats:
    """
    The summary the README quotes. Stored as JSON because it is one record, not a table.

    last_updated is a date rather than a timestamp: it used to carry microseconds, which meant every
    run dirtied this file even when the data underneath it had not changed at all.
    """

    make_count: int
    model_count: int
    style_count: int
    last_updated: str

    @classmethod
    def describe(cls, database: VehicleDatabase, last_updated: str) -> Stats:
        return cls(
            make_count=len(database.makes),
            model_count=len(database.models),
            style_count=len(database.styles),
            last_updated=last_updated,
        )


def read_stats(data_dir: Path | None = None) -> Stats:
    with open(data_path(STATS_JSON, data_dir), encoding="utf-8") as stats_file:
        return Stats(**json.load(stats_file))


def write_stats(stats: Stats, data_dir: Path | None = None) -> None:
    path = data_path(STATS_JSON, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "make_count": stats.make_count,
        "model_count": stats.model_count,
        "style_count": stats.style_count,
        "last_updated": stats.last_updated,
    }
    with open(path, mode="w", encoding="utf-8") as stats_file:
        stats_file.write(json.dumps(payload, indent=2) + "\n")
