# Open Vehicle DB

Vehicle database with makes / models / years / styles database for cars, trucks, SUV's, and other vehicles.

## What it contains

* 70 makes, e.g. "Toyota"
* 1,678 models, e.g. "Prius V"
* 9,960 styles, e.g. "PRIUS V 5DR HATCHBACK"
* Supports years from 1981 to 2027
* Last updated July 24, 2026

## How the data is stored

Four sorted CSV files in `data/`, one row per thing, joined on slugs:

| File | Rows | One row is |
| --- | --- | --- |
| `makes.csv` | 70 | a make, with the range of years it sold anything in |
| `models.csv` | 1,678 | a model, keyed by `(make_slug, model_slug)` |
| `styles.csv` | 9,960 | a style, keyed by `(make_slug, model_slug, style_name)` |
| `orphaned_styles.csv` | 1,084 | a style no model name could be matched to, with a count |

```csv
make_slug,model_slug,model_name,model_id,vehicle_type,years
acura,cl,CL,5145,car,"1987-1999,2001-2003"
```

Years are stored as compressed ranges, so a row stays one line no matter how many years it covers.
Rows are always written sorted by their key, which is what makes the interesting question — what did
the last update actually add? — easy to answer:

```shell
git log -p data/models.csv     # every model ever added or dropped, one line each
git diff --stat data/          # honest counts rather than reformatting noise
```

A new model is one added line. A model gaining a year is one changed line: `2018-2025` becomes
`2018-2026`. `data/CHANGELOG.md` says the same thing in prose, newest run first, and is written by the
update script.

`data/stats.json` is the summary quoted above. It stays JSON because it is one record rather than a
table.

## Working with the data in Python

Nothing passes raw dicts around. Every make, model, and style is a frozen dataclass from
`open_vehicle_db.models`, and `open_vehicle_db.storage` is the only thing that knows the files are CSV.

```
open_vehicle_db/
  models.py    Make, Model, Style, OrphanedStyle, VehicleType, VehicleDatabase
  storage.py   reads and writes data/, taking and returning those dataclasses
  years.py     "2018,2020-2022" <-> (2018, 2020, 2021, 2022)
  changes.py   diffing two datasets, which is what writes the changelog
  client.py    the read side: the queries below
```

## Setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/). Install it, then create the
environment from the lockfile:

```shell
uv sync
```

That also installs `open_vehicle_db` in editable mode, so the scripts and the client share one copy of
the dataclasses and no `PYTHONPATH` is needed. Run anything in the project with `uv run`:

```shell
uv run ./scripts/update_car_data.py            # refresh everything from the NHTSA API
uv run ./scripts/update_car_data.py toyota     # just one make, which is much quicker
```

Nothing in `data/` is written until every step of a run has finished, so a run that fails partway
leaves the committed data alone.

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

Both are configured in `pyproject.toml` to match this codebase: 4-space indents and a 120 character
line limit. The curated make whitelist/blacklist in `scripts/update_car_data.py` is wrapped in
`# fmt: off` / `# fmt: on` so it stays packed instead of exploding to one make per line.

## How to use it

```shell
uv run python clients/python/open_vehicle_db/client_usage_example.py
```

Makes and models can be looked up by name or by slug, case- and punctuation-insensitively, so
`"Alfa Romeo"`, `"ALFA ROMEO"`, and `"alfa_romeo"` all work.

### Get all the makes from a given year

```python
from open_vehicle_db import client

makes_2003 = client.list_makes_for_year(2003)
print([make.make_name for make in makes_2003])
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
print([model.model_name for model in models_2003_mazda])
['B-Series', 'Mazda6', 'MPV', 'MX-5', 'Protege', 'Tribute']
```

Results come back in the order the files are sorted in, which is by slug.

### List all the styles for a given year, make, and model

```python
from open_vehicle_db import client

styles_2003_mazda_protege = client.list_styles_for_year_make_model(year=2003, make="Mazda", model="Protege")
print([style.style_name for style in styles_2003_mazda_protege])
['MAZDASPEED PROTEGE 4DR SEDAN FWD', 'PROTEGE 4DR SEDAN LX/ES 2.0L', 'PROTEGE 4DR SEDAN SE 1.6L',
 'PROTEGE5 4DR WAGON FWD']
```

### Get one model, with every year it was sold in

```python
from open_vehicle_db import client

protege = client.get_model("Mazda", "Protege")
print(protege.vehicle_type, protege.years)
VehicleType.CAR (1990, 1991, 1992, 1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002, 2003)
```
