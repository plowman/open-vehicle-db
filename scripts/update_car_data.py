import json
from datetime import datetime

import re
import requests

VEHICLE_TYPE_ID_MAP = {
  1: {'VehicleTypeName': 'Motorcycle'},
  2: {'VehicleTypeName': 'Passenger Car'},
  3: {'VehicleTypeName': 'Truck'},
  5: {'VehicleTypeName': 'Bus'},
  6: {'VehicleTypeName': 'Trailer'},
  7: {'VehicleTypeName': 'Multipurpose Passenger Vehicle (MPV)'},
  9: {'VehicleTypeName': 'Low Speed Vehicle (LSV)'},
  10: {'VehicleTypeName': 'Incomplete Vehicle'},
  13: {"VehicleTypeName": "Off Road Vehicle"}
}

PASSENGER_VEHICLE_TYPE_IDS = {2, 3, 7}

CURRENT_YEAR = datetime.utcnow().year
YEAR_RANGE = range(1981, CURRENT_YEAR + 2)


def _make_api_request(path):
  url = f"https://vpic.nhtsa.dot.gov/api/vehicles{path}"
  if "&" in path:
    url += "&format=json"
  else:
    url += "?format=json"

  print(url)
  response = requests.get(url)
  return response.json().get("Results")


def slugify_string(input_string):
  slug = input_string.strip()
  slug = slug.lower()
  slug = slug.replace(" ", "_")
  slug = slug.replace(" ", "_")
  slug = slug.replace("-", "_")
  slug = re.sub("[^a-z0-9_]", "", slug)
  return slug


def get_all_makes():
  raw_makes_list = _make_api_request("/getallmakes")

  all_makes = []
  for make_data in raw_makes_list:
    make_name = make_data["Make_Name"].strip()
    make_slug = slugify_string(make_name)
    all_makes.append({
      "make_id": make_data["Make_ID"],
      "make_name": make_name,
      "make_slug": make_slug,
    })

  return all_makes


def get_types_for_make(make_name):
  raw_types_list = _make_api_request(f"/GetVehicleTypesForMake/{make_name}")
  print(raw_types_list)


def get_types_for_make_id(make_id):
  raw_types_list = _make_api_request(f"/GetVehicleTypesForMakeId/{make_id}")

  all_types = []
  for make_type in raw_types_list:
    all_types.append({
      'type_id': make_type.get("VehicleTypeId", "<missing>"),
      'type_name': make_type["VehicleTypeName"].strip(),
    })

  return all_types


def _get_model_dict(raw_model):
  return {
    "model_id": raw_model["Model_ID"],
    "model_name": raw_model["Model_Name"].strip(),
    "vehicle_type": "car",
    "years": [],
    "model_styles": {},
  }


def get_models_for_make_id(make_id):
  models = []

  raw_cars_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/car")
  for raw_model in raw_cars_list:
    models.append(_get_model_dict(raw_model))

  raw_trucks_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/truck")
  for raw_model in raw_trucks_list:
    models.append(_get_model_dict(raw_model))

  # Multi-purpose Passenger Vehicles: SUV's, Minivans, etc.
  raw_mpv_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/mpv")
  for raw_model in raw_mpv_list:
    models.append(_get_model_dict(raw_model))

  return models


def get_model_ids_for_make_and_year(make_id, year):
  model_ids = []
  models_in_year = _make_api_request(f"/getmodelsformakeidyear/makeId/{make_id}/modelyear/{year}")
  for model in models_in_year:
    model_ids.append(model["Model_ID"])

  return model_ids


def make_produces_passenger_vehicles(make_id):
  """
  Return true if this make produces cars or trucks.
  """
  make_types = get_types_for_make_id(make_id)
  make_type_ids = set([make_type["type_id"] for make_type in make_types])

  if not make_type_ids.issubset(VEHICLE_TYPE_ID_MAP.keys()):
    print(f"Found a new type?? {make_types}")

  # True if this make has any passenger vehicle types
  return bool(make_type_ids.intersection(PASSENGER_VEHICLE_TYPE_IDS))


def persist_json_file(file_name, data_dict):
  with open(file_name, mode="w") as json_file:
    json_file.write(json.dumps(data_dict, indent=2))


def load_json(file_name):
  with open(file_name) as json_file:
    json_data = json.loads(json_file.read())

  return json_data


grey_list = set()


def make_is_whitelisted(make):
  # Makes which create "mass market" cars or are otherwise well known
  white_list = {
    "smart", "yugo", "volkwagen", "volvo", "triumph", "toyota", "tesla", "suzuki", "subaru", "spyker",
    "saturn", "saab", "rolls_royce", "ram", "porsche", "pontiac", "plymouth", "peterbilt", "peugeot",
    "oldsmobile", "nissan", "mitsubishi", "mercury", "mercedes_benz", "mclaren", "mazda", "maybach",
    "maserati", "mini", "lotus", "lincoln", "lexus", "lamborghini", "karma", "kia", "jeep", "jaguar",
    "isuzu", "infiniti", "hyundai", "hummer", "honda", "honda", "gmc", "geo", "ford", "fiat", "ferrari",
    "fisker_automotive", "dodge", "datsun", "daimler", "daewoo", "chrysler", "chevrolet", "cadillac",
    "buick", "bugatti", "bentley", "bmw", "audi", "aston_martin", "alfa_romeo", "acura", "am_general"}

  # This should contain all of the other makes which technically produce cars but which nobody has heard of
  black_list = {}

  make_slug = make["make_slug"]
  if make_slug in white_list:
    return True

  if make_slug in black_list:
    return False

  print(f"ERROR: unrecognized make needs to be whitelisted or blacklisted: {make}")
  grey_list.add(make_slug)
  print(f"Unclassified makes: {grey_list}")

  return False


def get_vehicle_details(year=None, model=None, make=None):
  """
  Get the "Canadian" vehicle details for this year/model/make.

  These are the field descriptions from the API docs at https://vpic.nhtsa.dot.gov/api:
    MAKE  Vehicle Make
    MODEL	Vehicle Model
    MYR	  Signifies last two digits of the year in which the data was compiled for that specific model
    A	    Longitudinal distance between the center of the front bumper and the center of the base of the windshield	cm / inch
    B	    Passenger Car: Longitudinal distance between the center of the rear bumper and the center of the base of the backlight
          Station Wagon and Vans: Longitudinal distance between the backlight top moulding and the front door latch pillar
          Pick-ups: Longitudinal distance between the rearmost projection and the front door latch pillar	cm / inch
    C	    The maximum vertical height of the side glass	cm / inch
    D	    Vertical distance between the base of the side glass and the lower edge of the rocker panel	cm / inch
    E	    Distance between side rails or maximum width of top	cm / inch
    F	    Front overhang	cm / inch
    G	    Rear overhang	cm / inch
    OL	  Overall length	cm / inch
    OW	  Overall width	cm / inch
    OH	  Overall height	cm / inch
    WB	  Wheelbase	cm / inch
    TWF	  Front track width	cm / inch
    TWR	  Rear track width	cm / inch
    CW	  Curb weight	kg / lb
    WD	  Weight distribution (Front/Rear)	%
  """
  number_regex = re.compile("[^0-9]")

  url = f"/GetCanadianVehicleSpecifications/?Year={year or ''}&Make={make or ''}&Model={model or ''}&units="
  results = _make_api_request(url)
  vehicle_specifications = []
  for result in results:
    specs = result.get("Specs")
    raw_data = {}
    for spec in specs:
      spec_name = spec.get("Name")
      spec_value = spec.get("Value")
      if spec_value == "":
        spec_value = None
      elif spec_name not in ["Model", "Make", "WD"]:
        spec_value = number_regex.sub("", spec_value)
        if spec_value == "":
          print(f"BAD VALUE: {spec.get('Value')}")
          spec_value = None
        else:
          spec_value = int(spec_value)

      raw_data[spec_name] = spec_value

    if raw_data["Model"] is None:
      # This is rare but happens on occasion. See for instance:
      # https://vpic.nhtsa.dot.gov/api/vehicles/GetCanadianVehicleSpecifications/?Year=1982&Make=Ford&Model=&units=&format=json
      continue

    vehicle_specifications.append({
      "model_style": raw_data["Model"],
      "hood_length_cm": raw_data["A"],
      "back_length_cm": raw_data["B"],
      "side_glass_max_height_cm": raw_data["C"],
      "door_height_cm": raw_data["D"],
      "max_width_cm": raw_data["E"],
      "front_overhang_cm": raw_data["F"],
      "rear_overhang_cm": raw_data["G"],
      "overall_length_cm": raw_data["OL"],
      "overall_width_cm": raw_data["OW"],
      "overall_height_cm": raw_data["OH"],
      "wheelbase_cm": raw_data["WB"],
      "front_track_width_cm": raw_data["TWF"],
      "rear_track_width_cm": raw_data["TWR"],
      "curb_weight_kg": raw_data["CW"],
      "weight_distribution_pct": raw_data["WD"],
    })

  return vehicle_specifications


def update_makes_file():
  """
  Update makes.json with all of the NHTSA makes which currently produces cars or trucks.

  This takes roughly an hour or two to run.
  """
  filtered_makes = []
  all_makes = get_all_makes()
  all_makes = sorted(all_makes, key=lambda x: x["make_name"])
  for make in all_makes:
    if not make_produces_passenger_vehicles(make["make_id"]):
      # There are too many random car brands so we focus on just those makings cars and/or trucks
      continue

    if make["make_name"] == "FISKER AUTOMOTIVE":
      # This is a dumb name that doesn't match canada's name.
      make["make_name"] = "Fisker"
      make["make_slug"] = "fisker"

    if make_is_whitelisted(make):
      filtered_makes.append(make)
      print(f"{make['make_name']} produces passenger vehicles: {make}")

  persist_json_file("../data/makes.json", {"makes": filtered_makes})


def update_models_files():
  """
  Update models.json with the latest of makes and models from the
  """
  # all_makes = load_json("./makes.json")["makes"]
  all_makes = load_json("../data/models.json")
  for count, make in enumerate(all_makes):
    print("=" * 120)
    print("=" * 120)
    print(f"Updating Model {count + 1} / {len(all_makes)}: {make}")
    print("=" * 120)
    print("=" * 120)
    models = get_models_for_make_id(make["make_id"])
    first_year = None
    last_year = None
    print(models)

    for year in range(make["first_year"], make["last_year"] + 1):
      # 1981 is the earliest I see any models showing up in the API.
      model_ids_in_year = get_model_ids_for_make_and_year(make["make_id"], year)
      if model_ids_in_year:
        if not first_year:
          first_year = year
        last_year = year

      for model in models:
        if model["model_id"] in model_ids_in_year:
          model["years"].append(year)
    make["first_year"] = first_year
    make["last_year"] = last_year
    make["models"] = models
    print(models)

  persist_json_file("../data/models.json", all_makes)


def update_styles():
  all_makes = load_json("../data/models.json")
  all_mismatched_models = []

  for count, make in enumerate(all_makes):
    for year in range(make["first_year"], make["last_year"] + 1):
      details = get_vehicle_details(year=year, make=make["make_name"])
      all_upper_model_names = [model["model_name"].upper() for model in make["models"]]
      for detail in details:
        matching_list = [model_uc for model_uc in all_upper_model_names if detail["model_style"].startswith(model_uc)]
        if not matching_list:
          print(f"COULD NOT FIND MATCHING MODEL for details: {detail}")
          all_mismatched_models.append(make["make_name"] + " " + detail["model_style"])
        model_style_name = detail["model_style"]
        del detail["model_style"]
        for model in make["models"]:
          if model_style_name.startswith(model["model_name"].upper()):
            if model_style_name not in model["model_styles"]:
              model["model_styles"][model_style_name] = {
                "years": [year],
                "details": {
                  "<default>": detail,
                  year: "<default>",
                }
              }
            else:
              model_style_details = model["model_styles"][model_style_name]
              model_style_details["years"].append(year)
              if detail == model_style_details["details"]["<default>"]:
                model_style_details["details"][year] = "<default>"
              else:
                model_style_details["details"][year] = detail

    style_data = {}
    for model in make["models"]:
      style_data[model["model_name"]] = model["model_styles"]
    persist_json_file("./data/styles/" + make["make_slug"] + ".json", style_data)
    print(json.dumps(style_data, indent=2))

  print("ALL MODELS WE COULD NOT FIND:")
  for model in all_mismatched_models:
    print(model)


def update_everything():
  update_makes_file()
  update_models_files()
  update_styles()

# TODO: unify the makes and models files