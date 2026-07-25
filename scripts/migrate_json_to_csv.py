"""
One-shot conversion of the old nested JSON files into the CSVs described in the README.

Already run, and the JSON files it reads are gone from the tree, so this needs a checkout from before
they were removed to do anything. It is kept only so the conversion is reviewable rather than a thing
that happened once on someone's laptop, and can be deleted once you are happy with the CSVs:

    git stash && git checkout HEAD~1 -- data && uv run ./scripts/migrate_json_to_csv.py

It refuses to write anything unless the result still describes the same number of makes, models, and
styles that data/stats.json claims, which is how the conversion was checked.
"""

from __future__ import annotations

import json
import sys

from open_vehicle_db import storage
from open_vehicle_db.models import Make, Model, OrphanedStyle, Style, VehicleDatabase, VehicleType
from open_vehicle_db.slugs import slugify

OLD_MAKES_AND_MODELS_JSON = "makes_and_models.json"
OLD_ORPHANED_STYLES_JSON = "all_orphaned_styles.json"
OLD_STYLES_DIR = "styles"


def _load_old_json(*path_segments):
    path = storage.DATA_DIR.joinpath(*path_segments)
    with open(path, encoding="utf-8") as json_file:
        return json.load(json_file)


def _read_old_makes_and_models() -> tuple[list[Make], list[Model]]:
    makes = []
    models = []
    for raw_make in _load_old_json(OLD_MAKES_AND_MODELS_JSON):
        make = Make(
            make_slug=raw_make["make_slug"],
            make_id=raw_make["make_id"],
            make_name=raw_make["make_name"],
            first_year=raw_make.get("first_year"),
            last_year=raw_make.get("last_year"),
        )
        makes.append(make)

        for raw_model in raw_make["models"].values():
            models.append(
                Model.from_name(
                    make_slug=make.make_slug,
                    model_id=raw_model["model_id"],
                    model_name=raw_model["model_name"],
                    vehicle_type=VehicleType(raw_model["vehicle_type"]),
                    years=raw_model["years"],
                )
            )

    return makes, models


def _read_old_styles(models: list[Model]) -> list[Style]:
    """
    The old per-make style files key styles by model *name*, so those names are resolved back to the
    model slugs the CSVs join on. A name that no longer matches a model is a bug in the old data
    rather than something to paper over, so it is reported and skipped.
    """
    model_slugs_by_make = {}
    for model in models:
        model_slugs_by_make.setdefault(model.make_slug, {})[model.model_name] = model.model_slug

    styles = []
    unresolved = []
    for make_slug, model_slugs in sorted(model_slugs_by_make.items()):
        style_file = storage.DATA_DIR / OLD_STYLES_DIR / f"{make_slug}.json"
        if not style_file.exists():
            print(f"No style file for {make_slug}, skipping")
            continue

        for model_name, raw_styles in _load_old_json(OLD_STYLES_DIR, f"{make_slug}.json").items():
            model_slug = model_slugs.get(model_name)
            if model_slug is None:
                unresolved.append(f"{make_slug}/{model_name}")
                continue

            for style_name, style_data in raw_styles.items():
                styles.append(
                    Style(
                        make_slug=make_slug,
                        model_slug=model_slug,
                        style_name=style_name,
                        years=tuple(sorted(set(style_data["years"]))),
                    )
                )

    if unresolved:
        print(f"{len(unresolved)} style groups named a model that no longer exists: {unresolved[:10]}")

    return styles


def _read_old_orphaned_styles(makes: list[Make]) -> list[OrphanedStyle]:
    """
    The old file repeats an unmatched style once per year it appeared in. Those repeats carry no
    information the count does not, so they are tallied here.
    """
    make_slugs_by_name = {make.make_name: make.make_slug for make in makes}

    orphans = []
    for make_name, raw_orphans in _load_old_json(OLD_ORPHANED_STYLES_JSON).items():
        make_slug = make_slugs_by_name.get(make_name, slugify(make_name))
        occurrences_by_style = {}
        for style_name in raw_orphans["orphaned_styles"]:
            occurrences_by_style[style_name] = occurrences_by_style.get(style_name, 0) + 1

        for style_name, occurrences in occurrences_by_style.items():
            orphans.append(OrphanedStyle(make_slug=make_slug, style_name=style_name, occurrences=occurrences))

    return orphans


def _verify(database: VehicleDatabase) -> list[str]:
    """Check the conversion against the counts stats.json already claims, plus the CSV joins."""
    problems = []

    old_stats = storage.read_stats()
    for label, expected, found in [
        ("makes", old_stats.make_count, len(database.makes)),
        ("models", old_stats.model_count, len(database.models)),
        ("styles", old_stats.style_count, len(database.styles)),
    ]:
        if expected != found:
            problems.append(f"{label}: stats.json says {expected}, converted data has {found}")

    make_slugs = {make.make_slug for make in database.makes}
    model_keys = {(model.make_slug, model.model_slug) for model in database.models}

    orphaned_models = [model for model in database.models if model.make_slug not in make_slugs]
    if orphaned_models:
        problems.append(f"{len(orphaned_models)} models reference a missing make, e.g. {orphaned_models[0]}")

    orphaned_styles = [style for style in database.styles if (style.make_slug, style.model_slug) not in model_keys]
    if orphaned_styles:
        problems.append(f"{len(orphaned_styles)} styles reference a missing model, e.g. {orphaned_styles[0]}")

    duplicate_styles = len(database.styles) - len(
        {(style.make_slug, style.model_slug, style.style_name) for style in database.styles}
    )
    if duplicate_styles:
        problems.append(f"{duplicate_styles} styles share a make/model/name key")

    return problems


def main() -> int:
    makes, models = _read_old_makes_and_models()
    styles = _read_old_styles(models)
    orphaned_styles = _read_old_orphaned_styles(makes)
    database = VehicleDatabase(makes=makes, models=models, styles=styles)

    problems = _verify(database)
    if problems:
        print("Refusing to write the CSVs:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    storage.write_database(database)
    storage.write_orphaned_styles(orphaned_styles)

    print(
        f"Wrote {len(database.makes)} makes, {len(database.models)} models, {len(database.styles)} styles, "
        f"and {len(orphaned_styles)} unique orphaned styles."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
