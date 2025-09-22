from fastapi import FastAPI, Request
import random
import uuid
import torch
from typing import Optional
from models import GenerateRequest, RecipeOut, BulkRequest, UserPreferences, IngredientLine
from catalogs import (
    CAT_PROTEIN, CAT_STARCH, CAT_VEG, FLAVOR_PROFILES, pick_compatible, title_from, qty_for,
    respects_diet, gluten_swap, choose, estimated_cost, write_instructions, COMPAT
)
from ml_service import generate_ml_structured, embedder, get_user_embedding
from db_service import store_recipe, Session
from reco import router as reco_router

app = FastAPI(title="Margo-ML")
app.include_router(reco_router)

def _user_uuid_from_headers(request: Request) -> Optional[str]:
    for key in ("x-user-id", "x-user-uuid", "x-user"):
        v = request.headers.get(key)
        if not v:
            continue
        try:
            _ = uuid.UUID(v)
            return v
        except Exception:
            pass
    return None

def _ensure_embedding(recipe: dict) -> None:
    if recipe.get("embedding") is not None:
        return
    title = recipe.get("title") or ""
    ing_names = " ".join((i.get("name") or "") for i in recipe.get("ingredients", []) if isinstance(i, dict))
    instr = recipe.get("instructions") or ""
    text = " | ".join(filter(None, [title, ing_names, instr]))
    if text.strip():
        recipe["embedding"] = embedder.encode(text, batch_size=32).tolist()

def generate_structured(req: GenerateRequest) -> dict:
    profile = random.choice(FLAVOR_PROFILES)
    tech_pool = COMPAT.get(profile["name"], {}).get("tech")
    user_pref = set(req.techniques) if req.techniques else None
    if user_pref:
        inter = list((set(tech_pool) if tech_pool else set(t["techniques"] for t in FLAVOR_PROFILES)) & user_pref)
        technique = random.choice(inter or list(tech_pool or ["skillet", "sheet-pan", "one-pot"]))
    else:
        technique = random.choice(list(tech_pool or ["skillet", "sheet-pan", "one-pot", "stir-fry", "bake"]))

    protein = choose(CAT_PROTEIN, req.diet)
    if protein["name"] == "Eggs" and technique in {"stir-fry"}:
        technique = random.choice(["skillet", "bake", "one-pot"])

    allowed_starch = COMPAT.get(profile["name"], {}).get("starch")
    starch = gluten_swap(
        pick_compatible(CAT_STARCH, allowed_starch) if allowed_starch else choose(CAT_STARCH, req.diet),
        req.diet
    )

    allowed_veg = COMPAT.get(profile["name"], {}).get("veg")
    veg = pick_compatible(CAT_VEG, allowed_veg) if allowed_veg else choose(CAT_VEG, req.diet)

    ingredients = []
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

    recipe = {
        "id": None,
        "title": title,
        "servings": req.servings,
        "prepMinutes": prep,
        "cookMinutes": cook,
        "calories": None,
        "imageUrl": None,
        "tags": tags,
        "instructions": instructions,
        "tips": tips,
        "ingredients": [i.model_dump() for i in ingredients],
        "estimatedCostCents": cost,
    }
    return recipe

@app.post("/generate", response_model=RecipeOut)
def generate(req: GenerateRequest, request: Request):
    recipe = generate_structured(req)
    _ensure_embedding(recipe)
    user_id = _user_uuid_from_headers(request)
    recipe["id"] = store_recipe(recipe, user_id=user_id, source="heuristic", source_id=None, session_factory=Session)
    return recipe

@app.post("/generate_ml", response_model=RecipeOut)
def generate_ml(req: GenerateRequest, request: Request):
    if req.seed is not None:
        torch.manual_seed(req.seed)
    recipe = generate_ml_structured(req)
    _ensure_embedding(recipe)
    user_id = _user_uuid_from_headers(request)
    recipe["id"] = store_recipe(recipe, user_id=user_id, source="margo-ml", source_id=recipe.get("id"), session_factory=Session)
    return recipe

@app.post("/bulk_ml")
def bulk_ml(req: BulkRequest, request: Request):
    if req.seed is not None:
        random.seed(req.seed)
        torch.manual_seed(req.seed)
    out = []
    seen_titles = set()
    sv_opts = req.servingsOptions if req.servingsOptions else ([req.servings] if req.servings else [4])
    user_id = _user_uuid_from_headers(request)

    for _ in range(max(1, req.count)):
        sv = random.choice(sv_opts)
        one = generate_ml_structured(GenerateRequest(
            pantry=req.pantry,
            budgetCents=req.budgetCents,
            minutes=req.minutes,
            servings=sv,
            diet=req.diet,
            avoid=req.avoid,
            techniques=req.techniques,
            cuisine=req.cuisine,
            seed=req.seed
        ))
        if one["title"] in seen_titles:
            continue
        seen_titles.add(one["title"])
        _ensure_embedding(one)
        one["id"] = store_recipe(one, user_id=user_id, source="margo-ml", source_id=one.get("id"), session_factory=Session)
        out.append(one)
    return out

@app.post("/user_embedding")
def user_embedding(prefs: UserPreferences):
    return get_user_embedding(prefs)

@app.get("/health")
def health():
    return {"status": "ok"}