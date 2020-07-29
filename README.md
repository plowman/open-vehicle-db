# Open Vehicle DB
Vehicle database with makes / models / years / styles database for cars, trucks, SUV's, and other vehicles.

## What it contains
* 65 makes, e.g. "Toyota"
* 1,571 models, e.g. "Prius V"
* 8,871 styles, e.g. "PRIUS V 5DR HATCHBACK"
* Supports years from 1980 to 2021
* Last updated July 26, 2020

## How to use it
Here's an example in python:
```python
from open_vehicle_db import client

makes_2003 = client.list_makes_for_year(2003)
print([make["make_name"] for make in makes_2003])
# >>> ['Aston Martin', 'Jaguar', 'Maserati', 'Land Rover', 'Rolls Royce', 'Toyota', 'Mercedes-Benz', 'BMW', 'Bugatti', 'MINI', 'Ford', 'Lincoln', 'Mercury', 'Lotus', 'Chevrolet', 'Buick', 'Cadillac', 'GMC', 'Mazda', 'Honda', 'Acura', 'Dodge', 'Chrysler', 'Nissan', 'Infiniti', 'Mitsubishi', 'Jeep', 'Volvo', 'Fiat', 'Alfa Romeo', 'Peterbilt', 'Hyundai', 'Kia', 'Lamborghini', 'smart', 'Suzuki', 'Lexus', 'Subaru', 'Maybach', 'Pontiac', 'Isuzu', 'Triumph', 'SAAB', 'Audi', 'Bentley', 'Porsche', 'Ferrari', 'Daihatsu', 'Hummer', 'Saturn', 'Daewoo', 'Plymouth', 'Oldsmobile', 'YUGO', 'Peugeot']

models_2003_mazda = client.list_models_for_year_make(year=2003, make_name="Mazda")
print([model["model_name"] for model in models_2003_mazda])
# >>> ['MX-5', 'Mazda6', 'MPV', 'Protege', 'B-Series', 'Tribute']

styles_2003_mazda_protege = client.list_styles_for_year_make_model(year=2003, make="Mazda", model="Protege")
print([style["style_name"] for style in styles_2003_mazda_protege])
# >>> ['PROTEGE 4DR SEDAN LX/ES 2.0L', 'PROTEGE 4DR SEDAN SE 1.6L', 'PROTEGE5 4DR WAGON FWD', 'MAZDASPEED PROTEGE 4DR SEDAN FWD']
```

To use it in another language, you can just access the json files directly inside the data directory.
