import functools
import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime

import requests
from tqdm import tqdm

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

CURRENT_YEAR = datetime.now().year
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


def fetch_all_makes():
    raw_makes_list = _make_api_request("/getallmakes")

    all_makes = []
    for make_data in raw_makes_list:
        make_name = make_data["Make_Name"].strip()
        make_slug = slugify_string(make_name)
        all_makes.append({
            "make_id": make_data["Make_ID"],
            "make_name": make_name,
            "make_slug": make_slug,
            "models": {},
            "first_year": None,
            "last_year": None,
        })

    return all_makes


def fetch_types_for_make(make_name):
    raw_types_list = _make_api_request(f"/GetVehicleTypesForMake/{make_name}")
    print(raw_types_list)


def fetch_types_for_make_id(make_id):
    raw_types_list = _make_api_request(f"/GetVehicleTypesForMakeId/{make_id}")

    all_types = []
    for make_type in raw_types_list:
        all_types.append({
            'type_id': make_type.get("VehicleTypeId", "<missing>"),
            'type_name': make_type["VehicleTypeName"].strip(),
        })

    return all_types


def _get_model_dict(raw_model, vehicle_type=None):
    assert vehicle_type

    return {
        "model_id": raw_model["Model_ID"],
        "model_name": raw_model["Model_Name"].strip(),
        "vehicle_type": vehicle_type,
        "years": [],
        "model_styles": OrderedDict(),
    }


def fetch_models_for_make_id(make_id):
    models = []

    raw_cars_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/car")
    for raw_model in raw_cars_list:
        models.append(_get_model_dict(raw_model, vehicle_type="car"))

    raw_trucks_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/truck")
    for raw_model in raw_trucks_list:
        models.append(_get_model_dict(raw_model, vehicle_type="truck"))

    # Multi-purpose Passenger Vehicles: SUV's, Minivans, etc.
    raw_mpv_list = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/mpv")
    for raw_model in raw_mpv_list:
        models.append(_get_model_dict(raw_model, vehicle_type="mpv"))

    return models


def fetch_model_ids_for_make_and_year(make_id, year):
    model_ids = []
    models_in_year = _make_api_request(f"/getmodelsformakeidyear/makeId/{make_id}/modelyear/{year}")
    for model in models_in_year:
        model_ids.append(model["Model_ID"])

    return model_ids


@functools.cache
def make_produces_passenger_vehicles(make_id):
    """
    Return true if this make produces cars or trucks.
    """
    make_types = fetch_types_for_make_id(make_id)
    make_type_ids = set([make_type["type_id"] for make_type in make_types])

    if not make_type_ids.issubset(VEHICLE_TYPE_ID_MAP.keys()):
        print(f"Found a new type?? {make_types}")

    # True if this make has any passenger vehicle types
    return bool(make_type_ids.intersection(PASSENGER_VEHICLE_TYPE_IDS))


scripts_path = os.path.dirname(__file__)
project_root = os.path.dirname(scripts_path)


def path_to_file(*path_segments):
    return os.path.join(project_root, *path_segments)


def load_json(*json_path_segments):
    json_path = os.path.join(project_root, *json_path_segments)
    with open(json_path) as json_file:
        return json.loads(json_file.read())


def persist_json_file(data_dict, *json_path_segments):
    json_path = os.path.join(project_root, *json_path_segments)
    with open(json_path, mode="w") as json_file:
        json_file.write(json.dumps(data_dict, indent=2, sort_keys=False))


grey_list = set()

# Makes which create "mass market" cars or are otherwise well known
white_list = {
    "smart", "yugo", "volkwagen", "volvo", "triumph", "toyota", "tesla", "suzuki", "subaru", "spyker",
    "saturn", "saab", "rolls_royce", "ram", "porsche", "pontiac", "plymouth", "peterbilt", "peugeot",
    "oldsmobile", "nissan", "mitsubishi", "mercury", "mercedes_benz", "mclaren", "mazda", "maybach",
    "maserati", "mini", "lotus", "lincoln", "lexus", "lamborghini", "karma", "kia", "jeep", "jaguar",
    "isuzu", "infiniti", "hyundai", "hummer", "honda", "honda", "gmc", "geo", "ford", "fiat", "ferrari",
    "fisker", "dodge", "datsun", "daimler", "daewoo", "chrysler", "chevrolet", "cadillac",
    "buick", "bugatti", "bentley", "bmw", "audi", "aston_martin", "alfa_romeo", "acura", "am_general", "land_rover",
    "daihatsu", "rivian", "delorean", "shelby", "lucid"
}

# This should contain all of the other makes which technically produce cars but which nobody has heard of
black_list = {
    'sterling_motor_car', 'saw', 'bxr', 'zeligson', 'lancia', 'global_environmental_products_inc',
    'vintage_microbus',
    'ives_motors_corporation_imc', 'phoenix', 'protected_vehicles', 'laforza', 'western_star', 'volvo_truck',
    'sutphen',
    'panther', 'thnk', 'mycar', 'frontline', 'thomas_built', 'consulier', 'grumman', 'autocar', 'morgan',
    'azure_dynamic_inc', 'vector_aeromotive_corporation', 'blue_bird', 'spartan_motors',
    'utilimaster_motor_corporation', 'freightliner', 'osprey_custom_4x4', 'mack', 'gruppe_b', 'crane_carrier',
    'consulier_gtp', 'engine_connection', 'scammell', 'winnebago', 'outabout', 'ema', 'care_industries_ltd',
    'autocar_industries', 'avanti', 'xos', 'wheatridge', 'rocket_sled_motors', 'bug_motors', 'badger_equipment',
    'saleen', 'wausau_equipment_company', 'formula_1_street_com', 'alkane', 'pininfarina', 'london', 'california',
    'indiana_phoenix_inc', 'excalibur_automobile_corporation', 'international', 'rs_spider', 'lodal', 'polestar',
    'autokad', 'mosler', 'capacity_trucks', 'clenet', 'patriot_energy_services', 'jaspers_hot_rods_llc',
    'vision_industries', 'white', 'electric_mobile_cars', 'yester_year_auto', 'vironex', 'azure_dynamics',
    'matrix_motor_company', 'phoenix_sports_cars_inc', 'asuna', 'usa_motor_corporation',
    'mgs_grand_sport_mardikian',
    'pas', 'chanje', 'hmc', 'ev_innovations', 'beyond_roads', 'transpower', 'efficient_drivetrains_inc',
    'national_oilwell_varco', 'lite_car', 'precedent', 'envirotech_drive_systems_incorporated', 'renaissance',
    'fortunesport_ves', 'hino', 'workhorse', 'electric_vehicles_international', 'mini_big_trucks', 'autocar_ltd',
    'rage', 'mitsubishi_fuso', 'kalmar_industries_llc', 'nina', 'londoncoach_inc', 'service_king_manufacturing',
    'sprinter_dodge_or_freightliner', 'desoto_motors', 'execucoach_inc', 'ccc', 'american_lafrance', 'la_exotics',
    'tiger_truck_manufacturing', 'opel', 'moke_america', 'glickenhaus', 'cobra_cars', 'greenkraft',
    'global_fabricators', 'genesis', 'elgin_sweeper_co', 'truck_equipment_corporationtec',
    'hunter_automotive_group_inc', 'holden', 'sterling_truck', 'equus_automotive', 'collins', 'pagani',
    'marmon_motor_co', 'mahindra', 'american_motors', 'faw_jiaxing_happy_messenger', 'simon_duplex', 'ic_bus',
    'inzuro',
    'orange_ev_llc', 'iron_guru_customs', 'bbc', 'scuderia_cameron_glickenhaus_scg', 'oshkosh',
    'smith_electric_vehicles', 'njd_automotive_llc', 'federal_motors_inc', 'jlg', 'warhawk_performance',
    'westfall_motors_corp', 'contemporary_classic_cars_ccc', 'maxim_inc', 'zhejiang_kangdi_vehicles_co',
    'ottawa_brimont_corporation', 'jac_427', 'cx_automotive', 'whitegmc', 'e_one', 'boulder_electric_vehicle',
    'lumen',
    'korando', 'falcon', 'nanchang_freedom_technology_limited_company', 'heritage', 'merkur', 'caterpillar',
    'phoenix_motorcars', 'eagle', 'kimble_chassis', 'mcneilus', 'terrafugia', 'american_truck_company',
    'penske', 'rainier_truck_and_chassis', 'pierce_manufacturing', 'dennis', 'vintage_auto', 'byd', 'trident_motor',
    'steamroller_motorcycle_company_llc', 'winnebago_industries_inc', 'spv', 'brain_unlimited', 'koenigsegg',
    'allianz_sweeper_company', 'blackwater', 'us_specialty_vehicles_llc', 'jerr_dan', 'kimble', 'navistar',
    'avera_motors', 'creative_coachworks', 'general_purpose_vehicles', 'stanford_customs', 'coda', 'coachworks',
    'smit',
    'crane_carrier_company', 'ud', 'czinger', 'classic_roadsters', 'faradayfuture_inc',
    'gullwing_international_motors_ltd', 'canadian_electric_vehicles', 'cami', 'kovatch_mobile_equipment',
    'diamond_reo', 'ucc', 'vintage_cruiser', 'crown_energy_technologies', 'spartan_motors_chassis', 'kubvan',
    'revology', 'kenworth', 'armbruster_stageway', 'volkswagen', 'autodelta_usa_inc',
    'atlanta_fabricating__equipment_co', 'mana', 'terex_advance_mixer', 'hunter_design_group_llc',
    'the_vehicle_production_group', 'sti', 'ukeycheyma', 'orion_bus', 'panoz',
    'diamond_heavy_vehicle_solutions', 'daytona_coach_builders', 'kepler_motors', 'stoutbilt', 'superior_coaches',
    'vintage_rover', 'mobile_armoured_vehicle', 'humvee', 'making_you_mobile', 'c_r_cheetah_race_cars',
    'calaveras_mfg_inc', 'world_transport_authority', 'costin_sports_car', 'solectria', 'rig_works',
    'snowblast_sicard_inc', 'classic_sports_cars', 'bakkura_mobility', 'bluecar', 'sf_motors_inc'}


def make_is_whitelisted(make, warn_if_unlisted=False):
    make_slug = make["make_slug"]
    if make_slug in white_list:
        return True

    if make_slug in black_list:
        return False

    if warn_if_unlisted:
        print(f"ERROR: unrecognized make needs to be whitelisted or blacklisted: {make}")
        grey_list.add(make_slug)
        # print(f"Unclassified makes: {grey_list}")

    return False


def fetch_vehicle_details(year=None, model=None, make=None):
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
            spec_value = spec.get("Value").strip()
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


def fetch_passenger_makes():
    make_id_make_map = {}
    for vehicle_type in ["car", "truck", "mpv"]:
        results = _make_api_request(f"/GetMakesForVehicleType/{vehicle_type}")

        for result in results:
            make_id_make_map[result["MakeId"]] = {
                "first_year": None,
                "last_year": None,
                "make_name": result["MakeName"].strip(),
                "make_slug": slugify_string(result["MakeName"]),
                "make_id": result["MakeId"],
                "models": {},
            }

    return make_id_make_map.values()


def update_makes_file(target_make=None):
    """
    Update makes.json with all of the NHTSA makes which currently produces cars or trucks.

    This takes roughly an hour or two to run.
    """
    persisted_makes = load_make_models_json()
    persisted_makes_by_slug = {make["make_slug"]: make for make in persisted_makes}
    possible_new_makes = []

    makes_producing_passenger_vehicles = fetch_passenger_makes()
    for make in tqdm(makes_producing_passenger_vehicles):
        if make["make_name"] == "FISKER AUTOMOTIVE":
            # This is a dumb name that doesn't match canada's name.
            make["make_name"] = "Fisker"
            make["make_slug"] = "fisker"
        if make["make_id"] == 1033:
            # Skip the generic "FISKER" make, which lists no cars for some reason.
            continue
        if target_make and target_make != make["make_slug"]:
            continue

        make_slug = make["make_slug"]
        if make_slug not in persisted_makes_by_slug:
            if make_slug in white_list:
                # New make which was not previously known
                print(f"Adding a new make: {make}")
                persisted_makes_by_slug[make_slug] = make
            elif make_slug not in black_list:
                # Make which is not yet blacklisted
                possible_new_makes.append(make)
                print(f"Found an unlisted make which makes passenger vehicles: {make}")

    makes_and_models = list(sorted(persisted_makes_by_slug.values(), key=lambda make: make["make_slug"]))
    persist_json_file(makes_and_models, "data", "makes_and_models.json")

    for new_make in possible_new_makes:
        print(f"Found a possible new make: {new_make}")


def load_make_models_json():
    return load_json("data", "makes_and_models.json")


def update_models_files(target_make=None):
    """
    Update makes_and_models.json with the latest of makes and models.
    """
    all_makes = load_make_models_json()
    for make in tqdm(all_makes):
        if target_make and make.get("make_slug") != target_make:
            continue
        print("=" * 120)
        print("=" * 120)
        print(f"Updating Make id={make['make_id']} name={make['make_name']}")
        print("=" * 120)
        print("=" * 120)
        models = fetch_models_for_make_id(make["make_id"])
        first_year = None
        last_year = None
        print(models)

        for year in YEAR_RANGE:
            # 1981 is the earliest I see any models showing up in the API.
            model_ids_in_year = fetch_model_ids_for_make_and_year(make["make_id"], year)
            if model_ids_in_year:
                if not first_year:
                    first_year = year
                last_year = year

            for model in models:
                make["models"][model["model_name"]] = model
                if model["model_id"] in model_ids_in_year:
                    model["years"].append(year)
        make["first_year"] = first_year
        make["last_year"] = last_year
        print(models)

    persist_json_file(all_makes, "data", "makes_and_models.json")


not_alphanumeric = re.compile("[^A-Z0-9]")


def choose_matching_model_for_style(model_style_name, model_choices):
    """
    Fuzzy matching to try to connect Canadian styles to American model names
    """
    model_choices = set(model_choices)
    matching_models = []

    # Remove punctuation and capitalize both terms for easier comparison
    model_style_uc = model_style_name.replace("&", "And").upper()
    model_style_alphanumeric = not_alphanumeric.sub("", model_style_uc)
    model_choice_original_map = {}
    for model_choice in model_choices:
        model_choice_original_map[not_alphanumeric.sub("", model_choice.upper())] = model_choice
    model_choices_alphanumeric = model_choice_original_map.keys()

    # First check if the model_style starts with the name of any of our models
    for model_choice in model_choices_alphanumeric:
        if model_style_alphanumeric.startswith(model_choice):
            matching_models.append(model_choice_original_map[model_choice])

    if len(matching_models) == 1:
        return matching_models[0]

    # If that fails, look for overlap between a model and the model_style
    for model_choice in model_choices_alphanumeric:
        if model_choice in model_style_alphanumeric:
            matching_models.append(model_choice_original_map[model_choice])

    if len(matching_models) == 1:
        return matching_models[0]

    if len(matching_models) > 1:
        # If there are multiple matching, choose the largest match first. This mostly seems to work.
        matching_models = sorted(matching_models, key=lambda x: len(x), reverse=True)
        return matching_models[0]

    return None


def update_styles():
    all_makes = load_make_models_json()
    all_orphaned_styles = {}

    for count, make in enumerate(all_makes):
        if not (make["first_year"] and make["last_year"]):
            print(f"BAD MAKE missing first_year or last_year: {make}")
            continue
        print("Cool starting stuff now...")
        model_choices = make["models"].keys()
        all_orphaned_styles[make["make_name"]] = {
            "model_choices": list(model_choices),
            "orphaned_styles": [],
        }
        for year in range(make["first_year"], make["last_year"] + 1):
            details = fetch_vehicle_details(year=year, make=make["make_name"])
            for detail in details:
                model_style_name = detail["model_style"]
                del detail["model_style"]

                matching_model = choose_matching_model_for_style(model_style_name, model_choices)
                if matching_model:
                    model_styles = make["models"][matching_model]["model_styles"]
                    if model_style_name not in model_styles:
                        model_styles[model_style_name] = {
                            "years": [year],
                            # "details": {year: detail},
                        }
                    else:
                        model_styles[model_style_name]["years"].append(year)
                else:
                    all_orphaned_styles[make["make_name"]]["orphaned_styles"].append(model_style_name)
                    print(make["make_name"] + " could not find model style: " + model_style_name)

        print(f"Found orphans for make {make['make_name']}: \n {all_orphaned_styles[make['make_name']]}")

        style_data = OrderedDict()
        for model_key in sorted(make["models"]):
            style_data[model_key] = OrderedDict(make["models"][model_key]["model_styles"])
        persist_json_file(style_data, "data", "styles", make["make_slug"] + ".json")

    print("ALL MODELS WE COULD NOT FIND:")
    for make, values in all_orphaned_styles.items():
        print(f"For make {make}")
        print(f"Model choices: {values['model_choices']}")
        for orphaned_style in values["orphaned_styles"]:
            print(orphaned_style)

    print(all_orphaned_styles)
    persist_json_file(all_orphaned_styles, "data", "all_orphaned_styles.json")


def update_readme():
    """
    Update the readme with the latest stats.
    """
    make_models_data = load_make_models_json()
    make_count = len(make_models_data)
    model_count = sum(len(make_data["models"]) for make_data in make_models_data)
    max_make_year = max(make_data["last_year"] for make_data in make_models_data)
    min_make_year = min(make_data["first_year"] for make_data in make_models_data)

    style_count = 0
    make_slugs = [make_data["make_slug"] for make_data in make_models_data]
    for make_slug in make_slugs:
        make_style_data = load_json("data", "styles", f"{make_slug}.json")
        for model in make_style_data:
            for _ in make_style_data[model]:
                style_count += 1

    readme_content = open(path_to_file("README.md"), "r").read()

    # Replace the content after "## What it contains" but before "## How to use it" with new stats.
    old_data = readme_content.split("## What it contains")[1].split("## How to use it")[0]

    new_data = (
        "\n"
        f"* {make_count} makes, e.g.'Toyota'\n"
        f"* {model_count} models, e.g. 'Prius V'\n"
        f"* {style_count} styles, e.g. 'PRIUS V 5DR HATCHBACK'\n"
        f"* Supports years from {min_make_year} to {max_make_year}\n"
        f"* Last updated {datetime.now().strftime('%B %d, %Y')}\n"
        "\n"
    )

    print("=" * 100)
    print("Old data:")
    print(old_data)
    print("=" * 100)
    print("New data: ")
    print(new_data)

    readme_content = readme_content.replace(old_data, new_data)
    open(path_to_file("README.md"), "w").write(readme_content)


def update_everything():
    # update_makes_file(target_make="fisker")
    update_makes_file()
    # update_models_files(target_make="fisker")
    # update_models_files()
    # update_styles()
    # update_readme()


def main(args):
    print(f"Running update_car_data with args: {args}")
    update_everything()


if __name__ == "__main__":
    main(sys.argv[1:])
