"""
Comparing two datasets, so an update run can say what it actually changed.

The point of the CSV layout is that `git diff` is readable, but a diff still does not tell you at a
glance that a run added three models and extended year coverage on four hundred styles. This turns
the before and after into that summary, which update_car_data writes to data/CHANGELOG.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Make, Model, Style, VehicleDatabase
from .years import format_years

# How many individual entries to name before collapsing the rest into a count. Style additions in
# particular can run into the hundreds, and a changelog nobody reads is no better than no changelog.
MAX_ENTRIES_LISTED = 25


@dataclass(frozen=True, slots=True, order=True)
class YearChange:
    """A model or style whose identity is unchanged but whose year coverage moved."""

    label: str
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class DatabaseChanges:
    added_makes: tuple[Make, ...] = ()
    removed_makes: tuple[Make, ...] = ()
    added_models: tuple[Model, ...] = ()
    removed_models: tuple[Model, ...] = ()
    added_styles: tuple[Style, ...] = ()
    removed_styles: tuple[Style, ...] = ()
    model_year_changes: tuple[YearChange, ...] = ()
    style_year_changes: tuple[YearChange, ...] = ()

    # Slug to display name for every make on either side, so that the changelog can name the make a
    # new model belongs to even when that make itself is unchanged.
    make_names: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.added_makes,
                self.removed_makes,
                self.added_models,
                self.removed_models,
                self.added_styles,
                self.removed_styles,
                self.model_year_changes,
                self.style_year_changes,
            ]
        )

    @classmethod
    def between(cls, before: VehicleDatabase, after: VehicleDatabase) -> DatabaseChanges:
        makes_before = {make.make_slug: make for make in before.makes}
        makes_after = {make.make_slug: make for make in after.makes}

        models_before = {(model.make_slug, model.model_slug): model for model in before.models}
        models_after = {(model.make_slug, model.model_slug): model for model in after.models}

        styles_before = {(style.make_slug, style.model_slug, style.style_name): style for style in before.styles}
        styles_after = {(style.make_slug, style.model_slug, style.style_name): style for style in after.styles}

        make_names = {slug: make.make_name for slug, make in {**makes_before, **makes_after}.items()}

        model_year_changes = []
        for key, model in models_after.items():
            previous = models_before.get(key)
            if previous is not None and previous.years != model.years:
                label = f"{make_names.get(model.make_slug, model.make_slug)} {model.model_name}"
                model_year_changes.append(
                    YearChange(label=label, before=format_years(previous.years), after=format_years(model.years))
                )

        style_year_changes = []
        for key, style in styles_after.items():
            previous = styles_before.get(key)
            if previous is not None and previous.years != style.years:
                label = f"{make_names.get(style.make_slug, style.make_slug)} {style.style_name}"
                style_year_changes.append(
                    YearChange(label=label, before=format_years(previous.years), after=format_years(style.years))
                )

        def missing_from(source: dict, other: dict) -> tuple:
            return tuple(sorted(value for key, value in source.items() if key not in other))

        return cls(
            added_makes=missing_from(makes_after, makes_before),
            removed_makes=missing_from(makes_before, makes_after),
            added_models=missing_from(models_after, models_before),
            removed_models=missing_from(models_before, models_after),
            added_styles=missing_from(styles_after, styles_before),
            removed_styles=missing_from(styles_before, styles_after),
            model_year_changes=tuple(sorted(model_year_changes)),
            style_year_changes=tuple(sorted(style_year_changes)),
            make_names=make_names,
        )

    def summary_line(self) -> str:
        """One line fit for the end of a run's output."""
        if self.is_empty:
            return "No changes."

        parts = []
        for label, values in [
            ("make", self.added_makes),
            ("model", self.added_models),
            ("style", self.added_styles),
        ]:
            if values:
                parts.append(f"+{len(values)} {label}{'s' if len(values) != 1 else ''}")
        for label, values in [
            ("make", self.removed_makes),
            ("model", self.removed_models),
            ("style", self.removed_styles),
        ]:
            if values:
                parts.append(f"-{len(values)} {label}{'s' if len(values) != 1 else ''}")
        year_changes = len(self.model_year_changes) + len(self.style_year_changes)
        if year_changes:
            parts.append(f"{year_changes} year change{'s' if year_changes != 1 else ''}")

        return ", ".join(parts)

    def to_markdown(self, heading: str) -> str:
        lines = [f"## {heading}", ""]
        if self.is_empty:
            lines += ["No changes.", ""]
            return "\n".join(lines)

        lines += [self.summary_line(), ""]

        def describe_model(model: Model) -> str:
            make_name = self.make_names.get(model.make_slug, model.make_slug)
            return f"{make_name} {model.model_name} ({format_years(model.years) or 'no years'})"

        def describe_style(style: Style) -> str:
            make_name = self.make_names.get(style.make_slug, style.make_slug)
            return f"{make_name} {style.style_name} ({format_years(style.years) or 'no years'})"

        def section(title: str, entries: list[str]) -> None:
            if not entries:
                return
            lines.append(f"### {title} ({len(entries)})")
            lines.append("")
            for entry in entries[:MAX_ENTRIES_LISTED]:
                lines.append(f"* {entry}")
            if len(entries) > MAX_ENTRIES_LISTED:
                lines.append(f"* ...and {len(entries) - MAX_ENTRIES_LISTED} more")
            lines.append("")

        section("New makes", [f"{make.make_name} ({make.first_year}-{make.last_year})" for make in self.added_makes])
        section("Dropped makes", [make.make_name for make in self.removed_makes])
        section("New models", [describe_model(model) for model in self.added_models])
        section("Dropped models", [describe_model(model) for model in self.removed_models])
        section("New styles", [describe_style(style) for style in self.added_styles])
        section("Dropped styles", [describe_style(style) for style in self.removed_styles])
        section(
            "Model year changes",
            [f"{change.label}: {change.before} -> {change.after}" for change in self.model_year_changes],
        )
        section(
            "Style year changes",
            [f"{change.label}: {change.before} -> {change.after}" for change in self.style_year_changes],
        )

        return "\n".join(lines)
