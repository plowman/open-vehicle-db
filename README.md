# Open Vehicle DB

Vehicle database with makes / models / years / styles database for cars, trucks, SUV's, and other vehicles.

## What it contains

* 70 makes, e.g. "Toyota"
* 1,678 models, e.g. "Prius V"
* 9,960 styles, e.g. "PRIUS V 5DR HATCHBACK"
* Supports years from 1981 to 2027
* Last updated July 24, 2026

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/). Install it, then create the
environment from the lockfile:

```shell
uv sync
```

Run anything in the project with `uv run`, which keeps the environment in sync automatically:

```shell
uv run ./scripts/update_car_data.py
```

To add or change a dependency, use `uv add` / `uv remove` — both update `pyproject.toml` and
`uv.lock`, which should be committed together.

## Formatting and linting

Formatting and linting are handled by [ruff](https://docs.astral.sh/ruff/). **Run both of these
every time you change any Python code, before committing:**

```shell
uv run ruff format
uv run ruff check --fix
```

`ruff format` rewrites files in place; `ruff check --fix` applies the lint fixes it can and prints
whatever is left for you to fix by hand. To see what they would do without changing anything:

```shell
uv run ruff format --check
uv run ruff check
```

Both are configured in `pyproject.toml` to match this codebase: 2-space indents and a 120 character
line limit. The curated make whitelist/blacklist in `scripts/update_car_data.py` is wrapped in
`# fmt: off` / `# fmt: on` so it stays packed instead of exploding to one make per line.

## How to use it

The client reads the JSON data relative to the repo, so run it from a checkout with
`clients/python` on your `PYTHONPATH`:

```shell
PYTHONPATH=clients/python uv run python clients/python/open_vehicle_db/client_usage_example.py
```

### Get all the makes from a given year

```python
from open_vehicle_db import client

makes_2003 = client.list_makes_for_year(2003)
print([make["make_name"] for make in makes_2003])
['ACURA', 'ALFA ROMEO', 'ASTON MARTIN', 'AUDI', 'BENTLEY', 'BMW', 'BUGATTI', 'BUICK', 'CADILLAC', 'CHEVROLET',
 'CHRYSLER', 'DAEWOO', 'DAIHATSU', 'DODGE', 'FERRARI', 'FIAT', 'FORD', 'GMC', 'HONDA', 'HUMMER', 'HYUNDAI', 'INFINITI',
 'ISUZU', 'JAGUAR', 'JEEP', 'KIA', 'LAMBORGHINI', 'LAND ROVER', 'LEXUS', 'LINCOLN', 'LOTUS', 'MASERATI', 'MAYBACH',
 'MAZDA', 'MERCEDES-BENZ', 'MERCURY', 'MINI', 'MITSUBISHI', 'NISSAN', 'OLDSMOBILE', 'PETERBILT', 'PEUGEOT', 'PLYMOUTH',
 'PONTIAC', 'PORSCHE', 'ROLLS-ROYCE', 'SAAB', 'SATURN', 'SMART', 'SPYKER', 'SUBARU', 'SUZUKI', 'TOYOTA', 'TRIUMPH',
 'VOLVO', 'YUGO']
```

### Get all the models for a given year and make

```python
from open_vehicle_db import client

models_2003_mazda = client.list_models_for_year_make(year=2003, make_name="Mazda")
print([model["model_name"] for model in models_2003_mazda])
['MX-5', 'Mazda6', 'MPV', 'Protege', 'B-Series', 'Tribute']
```

### List all the styles for a given year, make, and model

```python
from open_vehicle_db import client

styles_2003_mazda_protege = client.list_styles_for_year_make_model(year=2003, make="Mazda", model="Protege")
print([style["style_name"] for style in styles_2003_mazda_protege])
['PROTEGE 4DR SEDAN LX/ES 2.0L', 'PROTEGE 4DR SEDAN SE 1.6L', 'PROTEGE5 4DR WAGON FWD',
 'MAZDASPEED PROTEGE 4DR SEDAN FWD']
```
