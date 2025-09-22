from typing import List, Dict
import random
from models import IngredientLine

COMPAT = {
    "Teriyaki": {"starch": {"Long-grain rice", "Quinoa"}, "veg": {"Broccoli", "Bell pepper", "Carrot", "Onion"}, "tech": {"skillet", "stir-fry", "one-pot"}},
    "Tomato‑Basil": {"starch": {"Pasta", "Couscous", "Quinoa", "Long-grain rice"}, "veg": {"Zucchini", "Spinach", "Onion", "Bell pepper"}, "tech": {"skillet", "one-pot", "bake"}},
    "Taco": {"starch": {"Tortillas", "Long-grain rice"}, "veg": {"Bell pepper", "Onion", "Spinach"}, "tech": {"skillet", "sheet-pan"}},
    "Cajun": {"starch": {"Long-grain rice", "Potatoes", "Pasta"}, "veg": {"Bell pepper", "Onion", "Spinach"}, "tech": {"skillet", "sheet-pan", "one-pot"}},
    "Lemon‑Herb": {"starch": {"Potatoes", "Long-grain rice", "Quinoa", "Couscous"}, "veg": {"Broccoli", "Zucchini", "Spinach", "Carrot", "Onion"}, "tech": {"skillet", "sheet-pan", "one-pot", "bake"}}
}

CAT_PROTEIN = [
    {"name": "Chicken breast", "unit": "lb", "sv": 0.5, "cents": 350},
    {"name": "Ground turkey", "unit": "lb", "sv": 0.5, "cents": 300},
    {"name": "Pork loin", "unit": "lb", "sv": 0.5, "cents": 320},
    {"name": "Firm tofu", "unit": "oz", "sv": 8, "cents": 250, "vegan": True, "vegetarian": True},
    {"name": "Chickpeas", "unit": "can", "sv": 0.5, "cents": 120, "vegan": True, "vegetarian": True},
    {"name": "Black beans", "unit": "can", "sv": 0.5, "cents": 120, "vegan": True, "vegetarian": True},
    {"name": "Eggs", "unit": "ct", "sv": 1, "cents": 25, "vegetarian": True},
]

CAT_STARCH = [
    {"name": "Long-grain rice", "unit": "cup", "sv": 0.5, "cents": 50, "gf": True},
    {"name": "Pasta", "unit": "oz", "sv": 2, "cents": 30, "gf_alt": {"name": "GF pasta", "unit": "oz", "sv": 2, "cents": 60}},
    {"name": "Potatoes", "unit": "lb", "sv": 0.5, "cents": 90, "gf": True},
    {"name": "Quinoa", "unit": "cup", "sv": 0.4, "cents": 120, "gf": True},
    {"name": "Tortillas", "unit": "ct", "sv": 2, "cents": 20, "gf_alt": {"name": "Corn tortillas", "unit": "ct", "sv": 2, "cents": 25}},
    {"name": "Couscous", "unit": "cup", "sv": 0.4, "cents": 100},
]

CAT_VEG = [
    {"name": "Broccoli", "unit": "cup", "sv": 0.5, "cents": 70},
    {"name": "Bell pepper", "unit": "ct", "sv": 0.5, "cents": 80},
    {"name": "Onion", "unit": "ct", "sv": 0.5, "cents": 50},
    {"name": "Zucchini", "unit": "ct", "sv": 0.5, "cents": 85},
    {"name": "Spinach", "unit": "cup", "sv": 1, "cents": 60},
    {"name": "Carrot", "unit": "ct", "sv": 0.5, "cents": 40},
]

FLAVOR_PROFILES = [
    {"name": "Lemon‑Herb", "adds": [{"name": "Garlic", "unit": "clove", "sv": 1, "cents": 10}, {"name": "Lemon", "unit": "", "sv": 0.5, "cents": 80}, {"name": "Parsley", "unit": "tbsp", "sv": 1, "cents": 15}], "tags": ["lemon", "herb"], "techniques": ["skillet", "one-pot", "sheet-pan"], "cuisine": ["mediterranean"]},
    {"name": "Teriyaki", "adds": [{"name": "Soy sauce", "unit": "tbsp", "sv": 1.5, "cents": 15}, {"name": "Brown sugar", "unit": "tbsp", "sv": 1, "cents": 5}, {"name": "Ginger", "unit": "tsp", "sv": 0.5, "cents": 10}], "tags": ["teriyaki", "sweet-savory"], "techniques": ["skillet", "stir-fry"], "cuisine": ["asian"]},
    {"name": "Tomato‑Basil", "adds": [{"name": "Crushed tomatoes", "unit": "cup", "sv": 0.5, "cents": 70}, {"name": "Basil", "unit": "tbsp", "sv": 1, "cents": 20}, {"name": "Garlic", "unit": "clove", "sv": 1, "cents": 10}], "tags": ["tomato", "italian"], "techniques": ["skillet", "one-pot", "bake"], "cuisine": ["italian"]},
    {"name": "Cajun", "adds": [{"name": "Cajun seasoning", "unit": "tsp", "sv": 1, "cents": 8}, {"name": "Paprika", "unit": "tsp", "sv": 0.5, "cents": 6}, {"name": "Onion", "unit": "ct", "sv": 0.25, "cents": 50}], "tags": ["spicy", "cajun"], "techniques": ["skillet", "sheet-pan", "one-pot"], "cuisine": ["southern"]},
    {"name": "Taco", "adds": [{"name": "Chili powder", "unit": "tsp", "sv": 1, "cents": 8}, {"name": "Cumin", "unit": "tsp", "sv": 1, "cents": 7}, {"name": "Lime", "unit": "", "sv": 0.5, "cents": 70}], "tags": ["mexican", "taco"], "techniques": ["skillet", "sheet-pan"], "cuisine": ["mexican"]},
]

def pick_compatible(options, allowed_names):
    pool = [o for o in options if o["name"] in allowed_names]
    return random.choice(pool if pool else options)

def title_from(profile, protein, starch, veg, technique):
    if starch["name"] == "Tortillas" or profile["name"] == "Taco":
        return f"{protein['name']} Tacos with {veg['name']}"
    if starch["name"] in {"Long-grain rice", "Quinoa"}:
        label = {"skillet": "Skillet", "sheet-pan": "Sheet‑Pan", "one-pot": "One‑Pot", "stir-fry": "Stir‑Fry", "bake": "Baked"}.get(technique, technique.capitalize())
        return f"{label} {profile['name']} {protein['name']} Bowls with {starch['name']} & {veg['name']}"
    label = {"skillet": "Skillet", "sheet-pan": "Sheet‑Pan", "one-pot": "One‑Pot", "stir-fry": "Stir‑Fry", "bake": "Baked"}.get(technique, technique.capitalize())
    return f"{label} {profile['name']} {protein['name']} with {starch['name']} & {veg['name']}"

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
    cook = min(35, minutes)
    prep = max(5, int(0.35 * cook))
    steps = []
    if technique == "sheet-pan":
        steps = [
            "Preheat oven to 425°F (220°C).",
            f"Toss {veg['name'].lower()} and {protein['name'].lower()} with oil, salt, and half the seasoning; spread on a sheet pan.",
            f"Roast 12–15 min, flip; add remaining seasoning and roast until browned and cooked through.",
            f"Meanwhile, cook {starch['name'].lower()} per package or preferred method.",
            "Finish with citrus/herbs if applicable. Serve hot."
        ]
    elif technique in ("skillet", "stir-fry", "one-pot"):
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