# Open Vehicle DB

Vehicle database with makes / models / years / styles database for cars, trucks, SUV's, and other vehicles.

## What it contains
* 65 makes, e.g.'Toyota'
* 1669 models, e.g. 'Prius V'
* 9725 styles, e.g. 'PRIUS V 5DR HATCHBACK'
* Supports years from 1981 to 2026
* Last updated February 21, 2025

## How to use it

### Get all the makes from a given year

```python
from open_vehicle_db import client

makes_2003 = client.list_makes_for_year(2003)
print([make["make_name"] for make in makes_2003])
['ACURA', 'ALFA ROMEO', 'ASTON MARTIN', 'AUDI', 'BENTLEY', 'BMW', 'BUGATTI', 'BUICK', 'CADILLAC', 'CHEVROLET',
 'CHRYSLER', 'DAEWOO', 'DAIHATSU', 'DODGE', 'FERRARI', 'FIAT', 'FORD', 'GMC', 'HONDA', 'HUMMER', 'HYUNDAI', 'INFINITI',
 'ISUZU', 'JAGUAR', 'JEEP', 'KIA', 'LAMBORGHINI', 'LAND ROVER', 'LEXUS', 'LINCOLN', 'LOTUS', 'MASERATI', 'MAYBACH',
 'MAZDA', 'MERCEDES-BENZ', 'MERCURY', 'MINI', 'MITSUBISHI', 'NISSAN', 'OLDSMOBILE', 'PETERBILT', 'PEUGEOT', 'PLYMOUTH',
 'PONTIAC', 'PORSCHE', 'ROLLS ROYCE', 'SAAB', 'SATURN', 'SMART', 'SUBARU', 'SUZUKI', 'TOYOTA', 'TRIUMPH', 'VOLVO',
 'YUGO']
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
