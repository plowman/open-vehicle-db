import json
import os

python_path = os.path.dirname(__file__)
clients_path = os.path.dirname(python_path)
project_root = os.path.dirname(clients_path)


def load_json(*json_path_segments):
  json_path = os.path.join(project_root, *json_path_segments)
  with open(json_path) as json_file:
    return json.loads(json_file.read())


def get_make_data():
  return load_json("data", "makes.json")


def get_model_data():
  return load_json("data", "makes_and_models.json")


def get_style_data(make_slug):
  return load_json("data", "styles", f"{make_slug}.json")


def list_makes_for_year(year):
  makes_that_year = []
  make_data = get_model_data()
  for make in make_data:
    if make["first_year"] <= year <= make["last_year"]:
      makes_that_year.append(make)

  return makes_that_year


def list_models_for_year_make(year=None, make_name=None):
  matching_models = []
  model_data = get_model_data()
  for make in model_data:
    if make_name != make["make_name"]:
      continue
    for model in make["models"]:
      if year in model["years"]:
        matching_models.append(model)

  return matching_models


def get_make_by_name(make_name):
  make_data = get_model_data()
  for make in make_data:
    if make["make_name"] == make_name:
      return make

  return None


def list_styles_for_year_make_model(year=None, make=None, model=None):
  matching_styles = []
  make_data = get_make_by_name(make)
  style_data = get_style_data(make_data["make_slug"])
  for model_key in style_data:
    if model != model_key:
      continue
    for style_name, style_info in style_data[model_key].items():
      if year in style_info["years"]:
        matching_styles.append(style_name)

  return matching_styles


makes_2003 = list_makes_for_year(2003)
print([make["make_name"] for make in makes_2003])

models_2003_mazda = list_models_for_year_make(year=2003, make_name="Mazda")
print([model["model_name"] for model in models_2003_mazda])

models_2003_mazda_protege = list_styles_for_year_make_model(year=2003, make="Mazda", model="Protege")
print(models_2003_mazda_protege)
