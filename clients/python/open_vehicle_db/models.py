"""
The vehicle data as dataclasses.

Everything that crosses a function boundary in this project is one of these types. The CSV rows in
data/ are an encoding of them and nothing else reads those rows directly: storage.py turns them into
dataclasses on the way in and back into rows on the way out.

Make / Model / Style are frozen so that a value can be shared without anyone quietly editing it.
Years are accumulated in plain sets while a dataset is being built, then frozen into a tuple when the
dataclass is constructed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from .slugs import slugify


class VehicleType(Enum):
    """The NHTSA vehicle types this project keeps. MPV covers SUVs, minivans, and crossovers."""

    CAR = "car"
    TRUCK = "truck"
    MPV = "mpv"


# Field order is the natural sort key and the CSV column order, which is why order=True is enough to
# sort a list of these into the order the files are written in.
@dataclass(frozen=True, slots=True, order=True)
class Make:
    make_slug: str
    make_id: int
    make_name: str
    # None when the API returns no models in any year, which happens to makes on their way out.
    first_year: int | None = None
    last_year: int | None = None

    @classmethod
    def from_name(cls, make_id: int, make_name: str, **kwargs) -> Make:
        make_name = make_name.strip()
        return cls(make_slug=slugify(make_name), make_id=make_id, make_name=make_name, **kwargs)

    def covers_year(self, year: int) -> bool:
        if self.first_year is None or self.last_year is None:
            return False
        return self.first_year <= year <= self.last_year


@dataclass(frozen=True, slots=True, order=True)
class Model:
    make_slug: str
    model_slug: str
    model_name: str
    model_id: int
    vehicle_type: VehicleType
    years: tuple[int, ...] = ()

    @classmethod
    def from_name(cls, make_slug: str, model_id: int, model_name: str, vehicle_type: VehicleType, years=()) -> Model:
        model_name = model_name.strip()
        return cls(
            make_slug=make_slug,
            model_slug=slugify(model_name),
            model_name=model_name,
            model_id=model_id,
            vehicle_type=vehicle_type,
            years=tuple(sorted(set(years))),
        )

    def covers_year(self, year: int) -> bool:
        return year in self.years


@dataclass(frozen=True, slots=True, order=True)
class Style:
    make_slug: str
    model_slug: str
    style_name: str
    years: tuple[int, ...] = ()

    def covers_year(self, year: int) -> bool:
        return year in self.years


@dataclass(frozen=True, slots=True, order=True)
class OrphanedStyle:
    """
    A style from the Canadian specs endpoint that no model name could be matched to.

    This is a report on the quality of the matching in update_car_data, not part of the database.
    Occurrences are counted rather than repeated: the endpoint lists the same unmatched style once
    per year it appears in, which used to put 2,397 rows in the file to describe 1,084 styles.
    """

    make_slug: str
    style_name: str
    occurrences: int = 1


@dataclass
class VehicleDatabase:
    """
    A whole dataset, with the indexes needed to answer the client's questions.

    The indexes are dicts of dataclasses keyed by slug, built once here, so that a lookup is a dict
    hit rather than a scan over every make.
    """

    makes: tuple[Make, ...] = ()
    models: tuple[Model, ...] = ()
    styles: tuple[Style, ...] = ()

    _make_by_slug: dict[str, Make] = field(init=False, repr=False, compare=False)
    _models_by_make: dict[str, tuple[Model, ...]] = field(init=False, repr=False, compare=False)
    _styles_by_model: dict[tuple[str, str], tuple[Style, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Sorted on the way in, so that a database built in memory compares equal to the same data
        # read back from the files, and so that whoever built it does not have to remember to sort.
        self.makes = tuple(sorted(self.makes))
        self.models = tuple(sorted(self.models))
        self.styles = tuple(sorted(self.styles))

        self._make_by_slug = {make.make_slug: make for make in self.makes}

        models_by_make = defaultdict(list)
        for model in self.models:
            models_by_make[model.make_slug].append(model)
        self._models_by_make = {slug: tuple(models) for slug, models in models_by_make.items()}

        styles_by_model = defaultdict(list)
        for style in self.styles:
            styles_by_model[(style.make_slug, style.model_slug)].append(style)
        self._styles_by_model = {key: tuple(styles) for key, styles in styles_by_model.items()}

    def make(self, make: str) -> Make | None:
        """Look a make up by slug or by name, in either case case-insensitively."""
        return self._make_by_slug.get(slugify(make))

    def models_for_make(self, make: str) -> tuple[Model, ...]:
        found = self.make(make)
        if found is None:
            return ()
        return self._models_by_make.get(found.make_slug, ())

    def model(self, make: str, model: str) -> Model | None:
        model_slug = slugify(model)
        for candidate in self.models_for_make(make):
            if candidate.model_slug == model_slug:
                return candidate
        return None

    def styles_for_model(self, make: str, model: str) -> tuple[Style, ...]:
        found = self.model(make, model)
        if found is None:
            return ()
        return self._styles_by_model.get((found.make_slug, found.model_slug), ())

    def makes_for_year(self, year: int) -> tuple[Make, ...]:
        return tuple(make for make in self.makes if make.covers_year(year))

    def models_for_year_make(self, year: int, make: str) -> tuple[Model, ...]:
        return tuple(model for model in self.models_for_make(make) if model.covers_year(year))

    def styles_for_year_make_model(self, year: int, make: str, model: str) -> tuple[Style, ...]:
        return tuple(style for style in self.styles_for_model(make, model) if style.covers_year(year))
