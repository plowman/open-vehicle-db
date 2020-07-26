from open_vehicle_db import client

makes_2003 = client.list_makes_for_year(2003)
print([make["make_name"] for make in makes_2003])

models_2003_mazda = client.list_models_for_year_make(year=2003, make_name="Mazda")
print([model["model_name"] for model in models_2003_mazda])

styles_2003_mazda_protege = client.list_styles_for_year_make_model(year=2003, make="Mazda", model="Protege")
print([style["style_name"] for style in styles_2003_mazda_protege])
