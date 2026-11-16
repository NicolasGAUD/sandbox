import json
c = json.load(open("criteria.json", encoding="utf-8"))
def ch(name): return next(x for x in c["choices"] if x["name"] == name)
c["yes_no"][0].update(
  yes=["a blurry photo", "an out of focus photo with motion blur", "a photo with camera shake"],
  no=["a sharp photo", "a sharp, detailed photo in focus", "a crisp high resolution photo"])
o = ch("place_type")["options"]
o.update({
 "factory": ["an abandoned factory interior with rusty machinery", "an old industrial hall with steel beams and pipes", "a derelict warehouse with broken windows"],
 "house": ["an old abandoned house", "a derelict house with broken windows and overgrown garden", "a farmhouse in ruins"],
 "hospital": ["an abandoned hospital corridor with peeling paint", "an old hospital room with beds", "a medical operating room"],
 "religious": ["the inside of an old church with pews and an altar", "a church with a bell tower", "a chapel with stained glass windows"],
 "castle": ["a medieval castle with stone towers", "castle ruins on a hill", "a fortress with stone walls"],
 "office": ["an abandoned office with desks and chairs", "a messy room with old computers and papers"],
 "architecture": ["a modern glass and concrete building", "contemporary architecture seen from below", "a tall skyscraper with a glass facade"],
 "street_art": ["a wall covered with colorful graffiti", "a large mural painted on a wall", "street art spray paint on concrete"],
 "bunker": ["a concrete military bunker", "a world war two blockhouse", "a dark concrete tunnel"],
 "bridge": ["an old stone bridge over a river", "a railway viaduct with arches", "a steel bridge"],
 "landscape": ["a landscape with mountains and sky", "a view of the sea and the coast", "a field with trees and countryside"],
 "graphic": ["an abstract photo with blurred colors and light", "an artistic photo with motion blur and long exposure", "an abstract pattern of lines and shapes", "a minimalist photo of geometric lines"],
 "macro": ["a macro close-up photo of a small object", "a close-up of a texture, rust or peeling paint", "a detail of a flower or a leaf"],
 "facade": ["the facade of a building with windows", "an old door and shutters on a wall", "a row of windows on a brick wall"],
 "street": ["a city street with houses on both sides", "a narrow old street with buildings"],
 "urban_landscape": ["a city skyline with buildings", "an urban view with roads, cranes and buildings"],
 "animal": ["a photo of an animal", "a bird perched on a branch", "an insect on a flower"],
 "plastic_arts": ["a statue or a sculpture", "a painting hanging on a wall", "an art installation in a gallery"],
})
def setopts(name, d): ch(name)["options"].update(d)
setopts("condition", {
 "good": ["a clean modern building in good condition", "a well maintained building with a freshly painted facade", "a new building with clean windows"],
 "degraded": ["an old weathered building with peeling paint and stains", "a neglected abandoned building", "a rusty derelict structure"],
 "ruin": ["a ruined building with collapsed walls and no roof", "a collapsed roof and rubble"]})
setopts("weather", {
 "sunny": ["a clear blue sky", "a sunny day with a blue sky and no clouds"],
 "few_clouds": ["a blue sky with a few small clouds", "a mostly blue sky with some clouds"],
 "mixed": ["a blue sky with scattered white clouds", "a partly cloudy sky"],
 "cloudy": ["an overcast sky covered with grey clouds", "a white cloudy sky"],
 "bad_weather": ["a dark stormy sky with black clouds", "a rainy day with heavy dark clouds"]})
setopts("sky", {
 "visible": ["a building against a blue sky with clouds", "an outdoor photo with the sky visible", "a landscape with sky"],
 "absent": ["a close-up of a wall", "an indoor photo of a room", "a photo of the walls and ceiling of a room"]})
setopts("time_of_day", {
 "day": ["a photo taken during the day in daylight", "a bright sunny day"],
 "dusk": ["a photo of a sunset or sunrise with an orange sky", "a photo at dusk in the blue hour"],
 "night": ["a photo taken at night in the dark", "a night photo with artificial lights"]})
setopts("person", {
 "front": ["a person looking at the camera", "a portrait of a person"],
 "back": ["a person seen from behind", "a person walking away"],
 "profile": ["a person in profile", "a person seen from the side"],
 "no": ["an empty place", "a place with nobody"]})
json.dump(c, open("criteria_siglip2.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
