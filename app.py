# margo-ml/app.py
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import random

app = FastAPI(title="Margo-ML")

# ---------- Models ----------
class IngredientLine(BaseModel):
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    form: Optional[str] = None

class GenerateRequest(BaseModel):
    pantry: List[str] = Field(default_factory=list)
    budgetCents: int = 1200
    minutes: int = 30
    servings: int = 2
    diet: List[str] = Field(default_factory=list)         # ["vegan","vegetarian","gluten-free"]
    avoid: List[str] = Field(default_factory=list)
    techniques: List[str] = Field(default_factory=list)   # ["sheet-pan","skillet","one-pot"]
    cuisine: List[str] = Field(default_factory=list)      # ["mexican","italian","asian"]

class RecipeOut(BaseModel):
    title: str
    servings: int
    prepMinutes: int
    cookMinutes: int
    calories: Optional[int] = None
    imageUrl: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    instructions: str
    tips: Optional[str] = None
    ingredients: List[IngredientLine]
    estimatedCostCents: int

class BulkRequest(BaseModel):
    count: int = 100
    servings: Optional[int] = None
    servingsOptions: Optional[List[int]] = None  # e.g., [1,2,3,4]
    minutes: int = 30
    budgetCents: int = 1500
    diet: List[str] = []
    avoid: List[str] = []
    techniques: List[str] = []
    cuisine: List[str] = []
    seed: Optional[int] = None
# ---------- Catalogs (compact but diverse) ----------
# cents ~= cost per "serving unit" (sv) for rough estimates
# --- Add near the catalogs ---
COMPAT = {
    "Teriyaki": {
        "starch": {"Long-grain rice","Quinoa"},
        "veg": {"Broccoli","Bell pepper","Carrot","Onion"},
        "tech": {"skillet","stir-fry","one-pot"}
    },
    "Tomato‑Basil": {
        "starch": {"Pasta","Couscous","Quinoa","Long-grain rice"},
        "veg": {"Zucchini","Spinach","Onion","Bell pepper"},
        "tech": {"skillet","one-pot","bake"}
    },
    "Taco": {
        "starch": {"Tortillas","Long-grain rice"},
        "veg": {"Bell pepper","Onion","Spinach"},
        "tech": {"skillet","sheet-pan"}
    },
    "Cajun": {
        "starch": {"Long-grain rice","Potatoes","Pasta"},
        "veg": {"Bell pepper","Onion","Spinach"},
        "tech": {"skillet","sheet-pan","one-pot"}
    },
    "Lemon‑Herb": {
        "starch": {"Potatoes","Long-grain rice","Quinoa","Couscous"},
        "veg": {"Broccoli","Zucchini","Spinach","Carrot","Onion"},
        "tech": {"skillet","sheet-pan","one-pot","bake"}
    }
}

def pick_compatible(options, allowed_names):
    pool = [o for o in options if o["name"] in allowed_names]
    return random.choice(pool if pool else options)

def title_from(profile, protein, starch, veg, technique):
    # “Tacos” or “Bowls” naming makes titles read more naturally
    if starch["name"] == "Tortillas" or profile["name"] == "Taco":
        return f"{protein['name']} Tacos with {veg['name']}"
    if starch["name"] in {"Long-grain rice","Quinoa"}:
        label = {"skillet":"Skillet","sheet-pan":"Sheet‑Pan","one-pot":"One‑Pot","stir-fry":"Stir‑Fry","bake":"Baked"}.get(technique, technique.capitalize())
        return f"{label} {profile['name']} {protein['name']} Bowls with {starch['name']} & {veg['name']}"
    label = {"skillet":"Skillet","sheet-pan":"Sheet‑Pan","one-pot":"One‑Pot","stir-fry":"Stir‑Fry","bake":"Baked"}.get(technique, technique.capitalize())
    return f"{label} {profile['name']} {protein['name']} with {starch['name']} & {veg['name']}"

def generate_structured(req: GenerateRequest) -> Dict:
    profile = random.choice(FLAVOR_PROFILES)
    # choose technique compatible with profile and (if given) user prefs
    tech_pool = COMPAT.get(profile["name"], {}).get("tech")
    user_pref = set(req.techniques) if req.techniques else None
    if user_pref:
        inter = list((tech_pool if tech_pool else set(t["techniques"] for t in FLAVOR_PROFILES)) & user_pref)
        technique = random.choice(inter or list(tech_pool or ["skillet","sheet-pan","one-pot"]))
    else:
        technique = random.choice(list(tech_pool or ["skillet","sheet-pan","one-pot","stir-fry","bake"]))

    protein = choose(CAT_PROTEIN, req.diet)
    # constrain awkward protein-tech combos (e.g., Stir‑Fry Eggs)
    if protein["name"] == "Eggs" and technique in {"stir-fry"}:
        technique = random.choice(["skillet","bake","one-pot"])

    # starch & veg compatibility
    allowed_starch = COMPAT.get(profile["name"], {}).get("starch")
    starch = gluten_swap( pick_compatible(CAT_STARCH, allowed_starch) if allowed_starch else choose(CAT_STARCH, req.diet), req.diet )

    allowed_veg = COMPAT.get(profile["name"], {}).get("veg")
    veg = pick_compatible(CAT_VEG, allowed_veg) if allowed_veg else choose(CAT_VEG, req.diet)

    ingredients: List[IngredientLine] = []
    for it in [protein, starch, veg] + profile["adds"]:
        ingredients.append(IngredientLine(
            name=it["name"],
            qty=qty_for(req.servings, it),
            unit=it.get("unit", ""),
            form=None
        ))

    base_items = [protein, starch, veg] + profile["adds"]
    cost = min(estimated_cost(req.servings, base_items), req.budgetCents)
    cook = min(35, req.minutes)
    prep = max(5, int(0.35 * cook))

    instructions = write_instructions(profile, technique, protein, starch, veg, req.servings, req.minutes)
    tips = "Use frozen veg if needed; adjust liquid for starch by ~1/4 cup."

    title = title_from(profile, protein, starch, veg, technique)
    tags = ["budget", "30-min", technique] + profile["tags"]

    return dict(
        title=title, servings=req.servings,
        prepMinutes=prep, cookMinutes=cook,
        calories=None, imageUrl=None, tags=tags,
        ingredients=[i.model_dump() for i in ingredients],
        instructions=instructions, tips=tips,
        estimatedCostCents=cost
    )

CAT_PROTEIN = [
    {"name":"Chicken breast","unit":"lb","sv":0.5,"cents":350},
    {"name":"Ground turkey","unit":"lb","sv":0.5,"cents":300},
    {"name":"Pork loin","unit":"lb","sv":0.5,"cents":320},
    {"name":"Firm tofu","unit":"oz","sv":8,"cents":250,"vegan":True,"vegetarian":True},
    {"name":"Chickpeas","unit":"can","sv":0.5,"cents":120,"vegan":True,"vegetarian":True},
    {"name":"Black beans","unit":"can","sv":0.5,"cents":120,"vegan":True,"vegetarian":True},
    {"name":"Eggs","unit":"ct","sv":1,"cents":25,"vegetarian":True},
]

CAT_STARCH = [
    {"name":"Long-grain rice","unit":"cup","sv":0.5,"cents":50,"gf":True},
    {"name":"Pasta","unit":"oz","sv":2,"cents":30,"gf_alt":{"name":"GF pasta","unit":"oz","sv":2,"cents":60}},
    {"name":"Potatoes","unit":"lb","sv":0.5,"cents":90,"gf":True},
    {"name":"Quinoa","unit":"cup","sv":0.4,"cents":120,"gf":True},
    {"name":"Tortillas","unit":"ct","sv":2,"cents":20,"gf_alt":{"name":"Corn tortillas","unit":"ct","sv":2,"cents":25}},
    {"name":"Couscous","unit":"cup","sv":0.4,"cents":100},
]

CAT_VEG = [
    {"name":"Broccoli","unit":"cup","sv":0.5,"cents":70},
    {"name":"Bell pepper","unit":"ct","sv":0.5,"cents":80},
    {"name":"Onion","unit":"ct","sv":0.5,"cents":50},
    {"name":"Zucchini","unit":"ct","sv":0.5,"cents":85},
    {"name":"Spinach","unit":"cup","sv":1,"cents":60},
    {"name":"Carrot","unit":"ct","sv":0.5,"cents":40},
]

FLAVOR_PROFILES = [
    {
        "name":"Lemon‑Herb",
        "adds":[{"name":"Garlic","unit":"clove","sv":1,"cents":10},
                {"name":"Lemon","unit":"","sv":0.5,"cents":80},
                {"name":"Parsley","unit":"tbsp","sv":1,"cents":15}],
        "tags":["lemon","herb"],
        "techniques":["skillet","one-pot","sheet-pan"],
        "cuisine":["mediterranean"]
    },
    {
        "name":"Teriyaki",
        "adds":[{"name":"Soy sauce","unit":"tbsp","sv":1.5,"cents":15},
                {"name":"Brown sugar","unit":"tbsp","sv":1,"cents":5},
                {"name":"Ginger","unit":"tsp","sv":0.5,"cents":10}],
        "tags":["teriyaki","sweet-savory"],
        "techniques":["skillet","stir-fry"],
        "cuisine":["asian"]
    },
    {
        "name":"Tomato‑Basil",
        "adds":[{"name":"Crushed tomatoes","unit":"cup","sv":0.5,"cents":70},
                {"name":"Basil","unit":"tbsp","sv":1,"cents":20},
                {"name":"Garlic","unit":"clove","sv":1,"cents":10}],
        "tags":["tomato","italian"],
        "techniques":["skillet","one-pot","bake"],
        "cuisine":["italian"]
    },
    {
        "name":"Cajun",
        "adds":[{"name":"Cajun seasoning","unit":"tsp","sv":1,"cents":8},
                {"name":"Paprika","unit":"tsp","sv":0.5,"cents":6},
                {"name":"Onion","unit":"ct","sv":0.25,"cents":50}],
        "tags":["spicy","cajun"],
        "techniques":["skillet","sheet-pan","one-pot"],
        "cuisine":["southern"]
    },
    {
        "name":"Taco",
        "adds":[{"name":"Chili powder","unit":"tsp","sv":1,"cents":8},
                {"name":"Cumin","unit":"tsp","sv":1,"cents":7},
                {"name":"Lime","unit":"","sv":0.5,"cents":70}],
        "tags":["mexican","taco"],
        "techniques":["skillet","sheet-pan"],
        "cuisine":["mexican"]
    },
]

def qty_for(servings: int, item: Dict) -> float:
    return round(max(1e-9, servings * item.get("sv", 0.5)), 2)

def respects_diet(item: Dict, diet: List[str]) -> bool:
    if not diet: return True
    if "vegan" in diet: return item.get("vegan") is True
    if "vegetarian" in diet: return item.get("vegan") is True or item.get("vegetarian") is True
    return True

def gluten_swap(starch: Dict, diet: List[str]) -> Dict:
    if "gluten-free" in diet and "gf" not in starch:
        return starch.get("gf_alt", starch)
    return starch

def choose(lst: List[Dict], diet: List[str]) -> Dict:
    pool = [x for x in lst if respects_diet(x, diet)]
    return random.choice(pool if pool else lst)

def estimated_cost(servings: int, items: List[Dict]) -> int:
    total = 0
    for it in items:
        total += qty_for(servings, it) * it.get("cents", 0)
    return int(total)

def write_instructions(profile: Dict, technique: str, protein: Dict, starch: Dict, veg: Dict, servings: int, minutes: int) -> str:
    # Template writer with technique‑specific steps
    cook = min(35, minutes); prep = max(5, int(0.35 * cook))
    steps = []
    if technique == "sheet-pan":
        steps = [
            "Preheat oven to 425°F (220°C).",
            f"Toss {veg['name'].lower()} and {protein['name'].lower()} with oil, salt, and half the seasoning; spread on a sheet pan.",
            f"Roast 12–15 min, flip; add remaining seasoning and roast until browned and cooked through.",
            f"Meanwhile, cook {starch['name'].lower()} per package or preferred method.",
            "Finish with citrus/herbs if applicable. Serve hot."
        ]
    elif technique in ("skillet","stir-fry","one-pot"):
        steps = [
            f"Heat 1 tbsp oil in a large skillet over medium‑high. Season {protein['name'].lower()}, sear 2–3 min.",
            f"Add aromatics/seasoning; stir in {veg['name'].lower()} and cook 2–3 min.",
            f"Add {starch['name'].lower()} and liquid as needed; cover and cook until tender.",
            "Adjust salt/acid; garnish and serve."
        ]
    else:
        steps = [
            "Prep all ingredients.",
            f"Cook {protein['name'].lower()} with spices; add vegetables.",
            f"Cook {starch['name'].lower()} separately; combine and finish.",
            "Serve warm."
        ]
    return "\n".join(f"{i+1}) {t}" for i, t in enumerate(steps))

@app.post("/generate", response_model=RecipeOut)
def generate(req: GenerateRequest):
    # single recipe (for on‑demand UX later)
    return generate_structured(req)

@app.post("/bulk")
def bulk(req: BulkRequest):

    if req.seed is not None:
        random.seed(req.seed)
    out = []
    seen_titles = set()
    sv_opts = req.servingsOptions if req.servingsOptions else ([req.servings] if req.servings else [4])
    for _ in range(max(1, req.count)):
        sv = random.choice(sv_opts)
        one = generate_structured(GenerateRequest(
            pantry=[], budgetCents=req.budgetCents, minutes=req.minutes, servings=sv,
            diet=req.diet, avoid=req.avoid, techniques=req.techniques, cuisine=req.cuisine
        ))
        # de‑dup by title
        if one["title"] in seen_titles:
            continue
        seen_titles.add(one["title"])
        out.append(one)
    return out

@app.get("/health")
def health():
    return {"status": "ok"}