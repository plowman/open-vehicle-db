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
  return load_json("data", "models.json")

def list_makes_for_year(year):
  makes_that_year = []
  make_data = get_model_data()
  for make in make_data:
    pass

  return makes_that_year


def list_models_for_make(make_name=None):
  model_data = load_json("data", "models.json")
