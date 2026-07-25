"""
Open Vehicle DB: makes, models, years, and styles for cars, trucks, and SUVs.

    from open_vehicle_db import client

    for model in client.list_models_for_year_make(year=2003, make_name="Mazda"):
        print(model.model_name, model.years)
"""

from .models import Make, Model, OrphanedStyle, Style, VehicleDatabase, VehicleType
from .years import format_years, parse_years

__all__ = [
    "Make",
    "Model",
    "OrphanedStyle",
    "Style",
    "VehicleDatabase",
    "VehicleType",
    "format_years",
    "parse_years",
]
