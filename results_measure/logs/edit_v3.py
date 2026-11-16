import json
c = json.load(open("criteria_siglip2.json", encoding="utf-8"))
o = next(x for x in c["choices"] if x["name"] == "place_type")["options"]
o["lighthouse"] = "a photo of a lighthouse"
o["facade"] = ["a photo of a building facade", "a photo of an old door or window on a facade", "the front of a house with a door and windows seen from the street", "a flat wall of a building with rows of windows"]
o["house"] = ["a photo of an old abandoned house", "a derelict house with broken windows and overgrown garden"]
o["graphic"] = ["a photo of signs, text, logos or posters", "a photo of a graphic design with lines, colors and patterns", "an abstract photo with blurred colors and light", "a close-up photo of geometric shapes and patterns"]
o["macro"] = ["a macro photo of a small detail", "a close-up of a texture, rust or peeling paint"]
o["castle"] = ["a photo of a castle", "a medieval castle with stone towers"]
json.dump(c, open("criteria_siglip2.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
