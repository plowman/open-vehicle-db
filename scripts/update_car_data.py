"""
Rebuild the data in data/ from the NHTSA vPIC API.

    uv run ./scripts/update_car_data.py            # everything
    uv run ./scripts/update_car_data.py toyota     # one make, for a quicker check

Each step takes the current dataset and returns a new one, and nothing is written until every step
has finished. A run that dies halfway through therefore leaves the committed data alone rather than
replacing it with whatever it had managed to fetch.
"""

from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone

import requests
from open_vehicle_db import storage
from open_vehicle_db.changes import DatabaseChanges
from open_vehicle_db.models import Make, Model, OrphanedStyle, Style, VehicleDatabase, VehicleType
from open_vehicle_db.storage import Stats
from requests.adapters import HTTPAdapter
from tqdm import tqdm
from urllib3.util.retry import Retry

VEHICLE_TYPE_ID_MAP = {
    1: {"VehicleTypeName": "Motorcycle"},
    2: {"VehicleTypeName": "Passenger Car"},
    3: {"VehicleTypeName": "Truck"},
    5: {"VehicleTypeName": "Bus"},
    6: {"VehicleTypeName": "Trailer"},
    7: {"VehicleTypeName": "Multipurpose Passenger Vehicle (MPV)"},
    9: {"VehicleTypeName": "Low Speed Vehicle (LSV)"},
    10: {"VehicleTypeName": "Incomplete Vehicle"},
    13: {"VehicleTypeName": "Off Road Vehicle"},
}

PASSENGER_VEHICLE_TYPE_IDS = {2, 3, 7}

CURRENT_YEAR = datetime.now(timezone.utc).year
YEAR_RANGE = range(1981, CURRENT_YEAR + 2)

# The API sits behind a rate limiter that answers with an HTML "403 Access Denied" page once it
# decides you are pushing too hard, and then keeps doing so for around ten minutes. Getting blocked
# costs far more than the parallelism saves, so keep this low. Measured over 100 requests: 1 worker
# is 333 req/min and 2 is 726 req/min, both clean, while 16 workers got ~two thirds of requests
# refused. Prefer sending fewer requests over sending them faster.
MAX_CONCURRENT_REQUESTS = 2

# Without a timeout a single stalled socket hangs the whole run indefinitely.
REQUEST_TIMEOUT_SECONDS = 30

_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        pool_maxsize=MAX_CONCURRENT_REQUESTS,
        max_retries=Retry(
            # Long enough to outlast a ~10 minute block: backoff doubles up to backoff_max, so this
            # waits roughly 2s, 4s, 8s, ... 120s, 120s between attempts.
            total=10,
            backoff_factor=2,
            backoff_max=120,
            # 403 is how this API signals rate limiting, so it has to be retried rather than raised.
            status_forcelist=[403, 429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        ),
    ),
)


def _make_api_request(path):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles{path}"
    if "&" in path:
        url += "&format=json"
    else:
        url += "?format=json"

    # Reuses the pooled connection, which avoids a fresh TLS handshake per request.
    response = _session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)

    # Fail with something readable. The rate limiter replies with an HTML page rather than JSON, so
    # otherwise this surfaces as a JSONDecodeError several frames from the actual cause.
    if response.status_code != 200:
        raise RuntimeError(f"{response.status_code} from {url}: {response.text[:200]!r}")

    return response.json().get("Results")


def _fetch_in_parallel(fetch_one, items, description=None):
    """
    Map fetch_one over items concurrently, returning results in the original order of items.

    Ordering matters: the CSV files are sorted so that changes are easy to read in a diff, so results
    must not depend on which request happens to finish first.
    """
    items = list(items)
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        results = executor.map(fetch_one, items)
        if description:
            results = tqdm(results, total=len(items), desc=description)
        return list(results)


@dataclass(frozen=True, slots=True)
class MakeVehicleType:
    type_id: int
    type_name: str


@dataclass(frozen=True, slots=True)
class VehicleSpecification:
    """
    One row from the Canadian specifications endpoint.

    Only make_name and model_style are used to build the styles; the measurements are carried along
    because they are the reason to be talking to this endpoint at all and are the obvious next thing
    to publish.
    """

    make_name: str | None
    model_style: str
    hood_length_cm: int | None = None
    back_length_cm: int | None = None
    side_glass_max_height_cm: int | None = None
    door_height_cm: int | None = None
    max_width_cm: int | None = None
    front_overhang_cm: int | None = None
    rear_overhang_cm: int | None = None
    overall_length_cm: int | None = None
    overall_width_cm: int | None = None
    overall_height_cm: int | None = None
    wheelbase_cm: int | None = None
    front_track_width_cm: int | None = None
    rear_track_width_cm: int | None = None
    curb_weight_kg: int | None = None
    weight_distribution_pct: str | None = None


def fetch_all_makes() -> list[Make]:
    return [
        Make.from_name(make_id=raw_make["Make_ID"], make_name=raw_make["Make_Name"])
        for raw_make in _make_api_request("/getallmakes")
    ]


def fetch_types_for_make_id(make_id) -> list[MakeVehicleType]:
    return [
        MakeVehicleType(
            type_id=raw_type.get("VehicleTypeId", -1),
            type_name=raw_type["VehicleTypeName"].strip(),
        )
        for raw_type in _make_api_request(f"/GetVehicleTypesForMakeId/{make_id}")
    ]


def fetch_models_for_make_id(make_slug: str, make_id: int) -> list[Model]:
    """
    Every model of a make, across the vehicle types this project keeps.

    A handful of models are listed under more than one type, so these are collapsed by slug with the
    last type winning. models.csv is keyed on (make_slug, model_slug) and cannot hold both.
    """
    models_by_slug = {}
    # Multi-purpose Passenger Vehicles ("mpv") are SUVs, minivans, and the like.
    for vehicle_type in VehicleType:
        raw_models = _make_api_request(f"/GetModelsForMakeIdYear/makeId/{make_id}/vehicleType/{vehicle_type.value}")
        for raw_model in raw_models:
            model = Model.from_name(
                make_slug=make_slug,
                model_id=raw_model["Model_ID"],
                model_name=raw_model["Model_Name"],
                vehicle_type=vehicle_type,
            )
            models_by_slug[model.model_slug] = model

    return list(models_by_slug.values())


def fetch_model_ids_for_make_and_year(make_id, year) -> set[int]:
    models_in_year = _make_api_request(f"/getmodelsformakeidyear/makeId/{make_id}/modelyear/{year}")
    return {model["Model_ID"] for model in models_in_year}


def make_produces_passenger_vehicles(make_id) -> bool:
    """
    Return true if this make produces cars or trucks.
    """
    make_types = fetch_types_for_make_id(make_id)
    make_type_ids = {make_type.type_id for make_type in make_types}

    if not make_type_ids.issubset(VEHICLE_TYPE_ID_MAP.keys()):
        print(f"Found a new type?? {make_types}")

    # True if this make has any passenger vehicle types
    return bool(make_type_ids.intersection(PASSENGER_VEHICLE_TYPE_IDS))


# These are hand-maintained lists, so they are kept packed rather than one make per line.
# fmt: off
# Makes which create "mass market" cars or are otherwise well known
WHITE_LIST = {
    "smart", "yugo", "volkwagen", "volvo", "triumph", "toyota", "tesla", "suzuki", "subaru", "spyker",
    "saturn", "saab", "rolls_royce", "ram", "porsche", "pontiac", "plymouth", "peterbilt", "peugeot",
    "oldsmobile", "nissan", "mitsubishi", "mercury", "mercedes_benz", "mclaren", "mazda", "maybach",
    "maserati", "mini", "lotus", "lincoln", "lexus", "lamborghini", "karma", "kia", "jeep", "jaguar",
    "isuzu", "infiniti", "hyundai", "hummer", "honda", "gmc", "geo", "ford", "fiat", "ferrari",
    "fisker", "dodge", "datsun", "daimler", "daewoo", "chrysler", "chevrolet", "cadillac",
    "buick", "bugatti", "bentley", "bmw", "audi", "aston_martin", "alfa_romeo", "acura", "am_general", "land_rover",
    "daihatsu", "renault", "rivian", "delorean", "shelby", "lucid",
}

# This should contain all of the other makes which technically produce cars but which nobody has heard of
BLACK_LIST = {
    'sterling_motor_car', 'saw', 'bxr', 'zeligson', 'lancia', 'global_environmental_products_inc', 'vintage_microbus',
    'ives_motors_corporation_imc', 'phoenix', 'protected_vehicles', 'laforza', 'western_star', 'volvo_truck', 'sutphen',
    'panther', 'thnk', 'mycar', 'frontline', 'thomas_built', 'consulier', 'grumman', 'autocar', 'morgan',
    'azure_dynamic_inc', 'vector_aeromotive_corporation', 'blue_bird', 'spartan_motors',
    'utilimaster_motor_corporation', 'freightliner', 'osprey_custom_4x4', 'mack', 'gruppe_b', 'crane_carrier',
    'consulier_gtp', 'engine_connection', 'scammell', 'winnebago', 'outabout', 'ema', 'care_industries_ltd',
    'autocar_industries', 'avanti', 'xos', 'wheatridge', 'rocket_sled_motors', 'bug_motors', 'badger_equipment',
    'saleen', 'wausau_equipment_company', 'formula_1_street_com', 'alkane', 'pininfarina', 'london', 'california',
    'indiana_phoenix_inc', 'excalibur_automobile_corporation', 'international', 'rs_spider', 'lodal', 'polestar',
    'autokad', 'mosler', 'capacity_trucks', 'clenet', 'patriot_energy_services', 'jaspers_hot_rods_llc',
    'vision_industries', 'white', 'electric_mobile_cars', 'yester_year_auto', 'vironex', 'azure_dynamics',
    'matrix_motor_company', 'phoenix_sports_cars_inc', 'asuna', 'usa_motor_corporation', 'mgs_grand_sport_mardikian',
    'pas', 'chanje', 'hmc', 'ev_innovations', 'beyond_roads', 'transpower', 'efficient_drivetrains_inc',
    'national_oilwell_varco', 'lite_car', 'precedent', 'envirotech_drive_systems_incorporated', 'renaissance',
    'fortunesport_ves', 'hino', 'workhorse', 'electric_vehicles_international', 'mini_big_trucks', 'autocar_ltd',
    'rage', 'mitsubishi_fuso', 'kalmar_industries_llc', 'nina', 'londoncoach_inc', 'service_king_manufacturing',
    'sprinter_dodge_or_freightliner', 'desoto_motors', 'execucoach_inc', 'ccc', 'american_lafrance', 'la_exotics',
    'tiger_truck_manufacturing', 'opel', 'moke_america', 'glickenhaus', 'cobra_cars', 'greenkraft',
    'global_fabricators', 'genesis', 'elgin_sweeper_co', 'truck_equipment_corporationtec',
    'hunter_automotive_group_inc', 'holden', 'sterling_truck', 'equus_automotive', 'collins', 'pagani',
    'marmon_motor_co', 'mahindra', 'american_motors', 'faw_jiaxing_happy_messenger', 'simon_duplex', 'ic_bus', 'inzuro',
    'orange_ev_llc', 'iron_guru_customs', 'bbc', 'scuderia_cameron_glickenhaus_scg', 'oshkosh',
    'smith_electric_vehicles', 'njd_automotive_llc', 'federal_motors_inc', 'jlg', 'warhawk_performance',
    'westfall_motors_corp', 'contemporary_classic_cars_ccc', 'maxim_inc', 'zhejiang_kangdi_vehicles_co',
    'ottawa_brimont_corporation', 'jac_427', 'cx_automotive', 'whitegmc', 'e_one', 'boulder_electric_vehicle', 'lumen',
    'korando', 'falcon', 'nanchang_freedom_technology_limited_company', 'heritage', 'merkur', 'caterpillar',
    'phoenix_motorcars', 'eagle', 'kimble_chassis', 'mcneilus', 'terrafugia', 'american_truck_company',
    'penske', 'rainier_truck_and_chassis', 'pierce_manufacturing', 'dennis', 'vintage_auto', 'byd', 'trident_motor',
    'steamroller_motorcycle_company_llc', 'winnebago_industries_inc', 'spv', 'brain_unlimited', 'koenigsegg',
    'allianz_sweeper_company', 'blackwater', 'us_specialty_vehicles_llc', 'jerr_dan', 'kimble', 'navistar',
    'avera_motors', 'creative_coachworks', 'general_purpose_vehicles', 'stanford_customs', 'coda', 'coachworks', 'smit',
    'crane_carrier_company', 'ud', 'czinger', 'classic_roadsters', 'faradayfuture_inc',
    'gullwing_international_motors_ltd', 'canadian_electric_vehicles', 'cami', 'kovatch_mobile_equipment',
    'diamond_reo', 'ucc', 'vintage_cruiser', 'crown_energy_technologies', 'spartan_motors_chassis', 'kubvan',
    'revology', 'kenworth', 'armbruster_stageway', 'volkswagen', 'autodelta_usa_inc',
    'atlanta_fabricating__equipment_co', 'mana', 'terex_advance_mixer', 'hunter_design_group_llc',
    'the_vehicle_production_group', 'sti', 'ukeycheyma', 'orion_bus', 'panoz',
    'diamond_heavy_vehicle_solutions', 'daytona_coach_builders', 'kepler_motors', 'stoutbilt', 'superior_coaches',
    'vintage_rover', 'mobile_armoured_vehicle', 'humvee', 'making_you_mobile', 'c_r_cheetah_race_cars',
    'calaveras_mfg_inc', 'world_transport_authority', 'costin_sports_car', 'solectria', 'rig_works',
    'snowblast_sicard_inc', 'classic_sports_cars', 'bakkura_mobility', 'bluecar', 'sf_motors_inc'
}
# fmt: on

# Makes seen in the API that are on neither list. Reported once at the end of a run.
grey_list = set()

# Unparseable spec values from the Canadian specs endpoint, tallied and reported once.
bad_spec_values = Counter()


def make_is_whitelisted(make: Make, warn_if_unlisted=True) -> bool:
    if make.make_slug in WHITE_LIST:
        return True

    if make.make_slug in BLACK_LIST:
        return False

    if warn_if_unlisted:
        # Only record it here. Printing the whole accumulated set on every miss is quadratic:
        # /getallmakes returns ~12,300 makes and almost none of them are listed.
        grey_list.add(make.make_slug)

    return False


def fetch_vehicle_details(year=None, model=None, make=None) -> list[VehicleSpecification]:
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
                    # Values like "***" or "NA". Counted rather than printed: one request now
                    # covers every make, so printing each one buries the rest of the output.
                    bad_spec_values[spec.get("Value")] += 1
                    spec_value = None
                else:
                    spec_value = int(spec_value)

            raw_data[spec_name] = spec_value

        if raw_data["Model"] is None:
            # This is rare but happens on occasion. See for instance:
            # https://vpic.nhtsa.dot.gov/api/vehicles/GetCanadianVehicleSpecifications/?Year=1982&Make=Ford&Model=&units=&format=json
            continue

        vehicle_specifications.append(
            VehicleSpecification(
                make_name=raw_data.get("Make"),
                model_style=raw_data["Model"],
                hood_length_cm=raw_data["A"],
                back_length_cm=raw_data["B"],
                side_glass_max_height_cm=raw_data["C"],
                door_height_cm=raw_data["D"],
                max_width_cm=raw_data["E"],
                front_overhang_cm=raw_data["F"],
                rear_overhang_cm=raw_data["G"],
                overall_length_cm=raw_data["OL"],
                overall_width_cm=raw_data["OW"],
                overall_height_cm=raw_data["OH"],
                wheelbase_cm=raw_data["WB"],
                front_track_width_cm=raw_data["TWF"],
                rear_track_width_cm=raw_data["TWR"],
                curb_weight_kg=raw_data["CW"],
                weight_distribution_pct=raw_data["WD"],
            )
        )

    return vehicle_specifications


def update_makes(database: VehicleDatabase, target_make=None) -> VehicleDatabase:
    """
    Refresh which makes exist and what they are called.

    Only make identity is decided here. Years come from update_models, so they are carried over from
    the make already on file rather than being reset.
    """
    makes_by_slug = {make.make_slug: make for make in database.makes}

    for make in fetch_all_makes():
        if make.make_name == "FISKER AUTOMOTIVE":
            # This is a dumb name that doesn't match canada's name.
            make = Make.from_name(make_id=make.make_id, make_name="Fisker")
        if make.make_id == 1033:
            # Skip the generic "FISKER" make, which lists no cars for some reason.
            continue
        if target_make and target_make != make.make_slug:
            continue

        if not make_is_whitelisted(make, warn_if_unlisted=True):
            # There are too many random car brands, so we focus on just those making cars and/or trucks
            continue

        known_make = makes_by_slug.get(make.make_slug)
        if known_make:
            makes_by_slug[make.make_slug] = replace(known_make, make_id=make.make_id, make_name=make.make_name)
        else:
            print(f"New make: {make.make_name}")
            makes_by_slug[make.make_slug] = make

    if grey_list:
        # Nearly every one of the ~12,300 makes the API returns is an unlisted trailer or bus
        # builder, so show a sample rather than the whole set.
        sample = sorted(grey_list)[:20]
        print(f"{len(grey_list)} makes are on neither the white nor the black list, e.g. {sample}")

    return replace(database, makes=tuple(sorted(makes_by_slug.values())))


def update_models(database: VehicleDatabase, target_make=None) -> VehicleDatabase:
    """
    Refresh the models of every make, along with the years each model and make was sold in.

    The bulk of the work is one request per make per year, so those are issued concurrently. Years are
    collected per model and sorted afterwards, since the requests do not finish in order.
    """
    targets = [make for make in database.makes if not target_make or make.make_slug == target_make]
    target_slugs = {make.make_slug for make in targets}

    # Models of makes this run is not touching are kept as they are; models whose make has gone away
    # entirely are dropped.
    known_slugs = {make.make_slug for make in database.makes}
    models = [
        model for model in database.models if model.make_slug not in target_slugs and model.make_slug in known_slugs
    ]
    makes = [make for make in database.makes if make.make_slug not in target_slugs]

    for make in tqdm(targets, desc="makes"):
        fetched_models = fetch_models_for_make_id(make.make_slug, make.make_id)

        # 1981 is the earliest I see any models showing up in the API.
        model_ids_per_year = _fetch_in_parallel(
            lambda year, make_id=make.make_id: fetch_model_ids_for_make_and_year(make_id, year),
            YEAR_RANGE,
        )

        years_by_model_id = defaultdict(set)
        first_year = None
        last_year = None
        for year, model_ids_in_year in zip(YEAR_RANGE, model_ids_per_year, strict=True):
            if model_ids_in_year:
                if not first_year:
                    first_year = year
                last_year = year

            for model in fetched_models:
                if model.model_id in model_ids_in_year:
                    years_by_model_id[model.model_id].add(year)

        models.extend(
            replace(model, years=tuple(sorted(years_by_model_id[model.model_id]))) for model in fetched_models
        )
        makes.append(replace(make, first_year=first_year, last_year=last_year))

    return replace(database, makes=tuple(sorted(makes)), models=tuple(sorted(models)))


not_alphanumeric = re.compile("[^A-Z0-9]")


def choose_matching_model_for_style(model_style_name, model_choices):
    """
    Fuzzy matching to try to connect Canadian styles to American model names
    """
    # Sorted, not a set: iteration order decides which model a style ends up under when several
    # match equally well, and set order varies between runs because string hashing is randomised.
    model_choices = sorted(set(model_choices))
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
        # Styles such as "SATURN SW1/SW2 4DR WAGON" name two models of the same length, so break
        # that tie on the name to keep the choice stable from one run to the next.
        matching_models = sorted(matching_models, key=lambda x: (-len(x), x))
        return matching_models[0]

    return None


def _fetch_styles_by_year(years) -> dict[int, list[VehicleSpecification]]:
    """
    Fetch the Canadian specs for every make, one request per year.

    Passing an empty Make returns every make for that year, so this needs one request per year rather
    than one per make per year.
    """
    details_per_year = _fetch_in_parallel(
        lambda year: fetch_vehicle_details(year=year),
        years,
        description="style years",
    )
    return dict(zip(years, details_per_year, strict=True))


def _make_name_matches(make_name, detail_make_name) -> bool:
    """
    Replicate how the API's Make filter behaves, which is a case-insensitive substring match.

    It matters: querying Make=RAM is how the API returns the rows it files under "RAM TRUCKS".
    """
    return make_name.upper() in (detail_make_name or "").upper()


def update_styles(database: VehicleDatabase) -> tuple[VehicleDatabase, list[OrphanedStyle]]:
    """
    Rebuild every style by matching the Canadian specs rows onto the models from update_models.

    Styles that no model name could be matched to are returned separately as a report on how well the
    matching is doing, rather than being mixed into the data.
    """
    datable_makes = []
    for make in database.makes:
        if make.first_year and make.last_year:
            datable_makes.append(make)
        else:
            print(f"BAD MAKE missing first_year or last_year: {make.make_slug}")

    if not datable_makes:
        return database, []

    models_by_make = {make.make_slug: database.models_for_make(make.make_slug) for make in datable_makes}

    # One request per year covering every make, instead of one per make per year.
    all_years = range(
        min(make.first_year for make in datable_makes),
        max(make.last_year for make in datable_makes) + 1,
    )
    details_by_year = _fetch_styles_by_year(all_years)

    # Keyed by (make_slug, model_slug, style_name). The endpoint lists a style once per year it was
    # sold in, so years accumulate here and are frozen into Style objects at the end.
    years_by_style = defaultdict(set)
    orphan_counts = Counter()

    for make in datable_makes:
        models_by_name = {model.model_name: model for model in models_by_make[make.make_slug]}
        for year in range(make.first_year, make.last_year + 1):
            for detail in details_by_year[year]:
                if not _make_name_matches(make.make_name, detail.make_name):
                    continue

                matching_model_name = choose_matching_model_for_style(detail.model_style, models_by_name.keys())
                if matching_model_name is None:
                    orphan_counts[(make.make_slug, detail.model_style)] += 1
                    continue

                model = models_by_name[matching_model_name]
                years_by_style[(make.make_slug, model.model_slug, detail.model_style)].add(year)

    # Styles of makes that were skipped above are kept rather than quietly dropped.
    skipped_slugs = {make.make_slug for make in database.makes} - {make.make_slug for make in datable_makes}
    styles = [style for style in database.styles if style.make_slug in skipped_slugs]
    styles.extend(
        Style(make_slug=make_slug, model_slug=model_slug, style_name=style_name, years=tuple(sorted(years)))
        for (make_slug, model_slug, style_name), years in years_by_style.items()
    )

    orphaned_styles = [
        OrphanedStyle(make_slug=make_slug, style_name=style_name, occurrences=occurrences)
        for (make_slug, style_name), occurrences in orphan_counts.items()
    ]

    print(f"Could not match {len(orphaned_styles)} styles to a model. See data/orphaned_styles.csv.")
    if bad_spec_values:
        print(f"Unparseable spec values, by value: {dict(bad_spec_values)}")

    return replace(database, styles=tuple(sorted(styles))), orphaned_styles


def update_everything(target_make=None) -> None:
    # Order matters: models needs the makes, styles needs the models.
    before = storage.load_database(missing_ok=True)
    after = update_makes(before, target_make)
    after = update_models(after, target_make)
    after, orphaned_styles = update_styles(after)

    changes = DatabaseChanges.between(before, after)
    today = datetime.now(timezone.utc).date().isoformat()

    # Nothing has touched data/ until this point, so a run that failed above leaves it intact.
    storage.write_database(after)
    storage.write_orphaned_styles(orphaned_styles)
    storage.write_stats(Stats.describe(after, last_updated=today))
    if not changes.is_empty:
        storage.prepend_changelog(changes.to_markdown(heading=today))

    print(f"{len(after.makes)} makes, {len(after.models)} models, {len(after.styles)} styles.")
    print(f"Changes since the last run: {changes.summary_line()}")


def main(args) -> None:
    target_make = args[0] if args else None
    if target_make:
        print(f"Updating {target_make} only")
    update_everything(target_make=target_make)


if __name__ == "__main__":
    main(sys.argv[1:])
