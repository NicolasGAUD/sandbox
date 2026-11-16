import json
old = json.load(open("criteria.json", encoding="utf-8"))
c = json.load(open("criteria_siglip2.json", encoding="utf-8"))
def ch(d, n): return next(x for x in d["choices"] if x["name"] == n)
def L(x): return [x] if isinstance(x, str) else list(x)
po, pn = ch(old, "place_type")["options"], ch(c, "place_type")["options"]
for k in ["landscape", "religious", "castle", "factory", "bunker", "bridge", "office"]:
    pn[k] = L(pn[k]) + L(po[k])
for k in ["lighthouse", "cellar", "cave", "cemetery", "farm", "mill", "railway", "guard_house", "vineyard_hut"]:
    pn[k] = L(po[k]) * 1 + ([f"an old {k.replace('_',' ')}"] if False else [])
pn["lighthouse"] = ["a lighthouse on a coast", "a photo of a lighthouse"]
pn["cellar"] = ["an underground vaulted cellar with stone arches", "a dark basement"]
pn["guard_house"] = L(po["guard_house"])
ch(c, "condition")["options"] = ch(old, "condition")["options"]
c["yes_no"][0] = old["yes_no"][0]
json.dump(c, open("criteria_siglip2.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
