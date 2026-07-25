"""
The read side of the database.

Every one of these returns Make / Model / Style dataclasses, never dicts. The CSVs are read once and
indexed, so repeated lookups do not re-parse the files or scan every make.
"""

from __future__ import annotations

from functools import lru_cache

from . import storage
from .models import Make, Model, Style, VehicleDatabase


@lru_cache(maxsize=1)
def database() -> VehicleDatabase:
    """The whole dataset, loaded on first use and then reused."""
    return storage.load_database()


def reload() -> VehicleDatabase:
    """Drop the cached dataset and read it again. Useful after an update run in the same process."""
    database.cache_clear()
    return database()


def list_all_makes() -> tuple[Make, ...]:
    return database().makes


def get_make_by_name(make_name: str) -> Make | None:
    """Find a make by name or slug, case- and punctuation-insensitively: "Alfa Romeo" or "alfa_romeo"."""
    return database().make(make_name)


def list_makes_for_year(year: int) -> tuple[Make, ...]:
    return database().makes_for_year(year)


def list_models_for_make(make_name: str) -> tuple[Model, ...]:
    return database().models_for_make(make_name)


def list_models_for_year_make(year: int, make_name: str) -> tuple[Model, ...]:
    return database().models_for_year_make(year, make_name)


def get_model(make_name: str, model_name: str) -> Model | None:
    return database().model(make_name, model_name)


def list_styles_for_make_model(make: str, model: str) -> tuple[Style, ...]:
    return database().styles_for_model(make, model)


def list_styles_for_year_make_model(year: int, make: str, model: str) -> tuple[Style, ...]:
    return database().styles_for_year_make_model(year, make, model)
