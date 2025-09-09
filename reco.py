# margo-ml/reco.py
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Set, Tuple
import math

router = APIRouter()

# ---- Models from the contract ----
class UserProfileIn(BaseModel):
    priceSensitivity: float = 0.5
    diet: List[str] = []
    dislikedIngredients: List[str] = []
    likedCuisines: List[str] = []
    minutesMax: Optional[int] = None
    householdSize: int = 1
    difficulty: Optional[str] = None          # 'beginner'|'intermediate'|'advanced'
    maxSteps: Optional[int] = None

class IngredientIn(BaseModel):
    id: Optional[str] = None
    name: str
    qty: Optional[float] = None
    unit: Optional[str] = None
    priceCents: Optional[int] = None          # per-line price if known

class Candidate(BaseModel):
    id: str
    title: str
    minutesTotal: int
    servings: int = 1
    estimatedCostCents: int
    cuisines: List[str] = []
    tags: List[str] = []
    ingredients: List[IngredientIn] = []
    embedding: Optional[List[float]] = None   # optional 384f

class RankRequest(BaseModel):
    user: UserProfileIn
    pantry: List[str] = Field(default_factory=list)
    budgetDayCents: Optional[int] = None
    k: int = 40
    candidates: List[Candidate]

class RankItem(BaseModel):
    recipeId: str
    title: str
    score01: float
    score10: float
    estimatedCostCents: int
    minutesTotal: int
    reasons: List[Dict[str, str]] = Field(default_factory=list)
    missing: List[Dict[str, str]] = Field(default_factory=list)

class PlanSuggestRequest(BaseModel):
    user: UserProfileIn
    pantry: List[str] = Field(default_factory=list)
    startDate: str
    days: int = 7
    slots: Dict[str, bool] = {"dinner": True}
    budgetWeekCents: int
    candidates: List[Candidate]

class PlanDay(BaseModel):
    index: int
    dinner: Optional[RankItem] = None
    lunch: Optional[RankItem] = None
    breakfast: Optional[RankItem] = None
    snack: Optional[RankItem] = None

class PlanOut(BaseModel):
    startDate: str
    days: List[PlanDay]
    estimatedTotalCents: int

# ---- Utils ----
def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b): return 0.0
    num = sum(x*y for x,y in zip(a,b))
    da = math.sqrt(sum(x*x for x in a)); db = math.sqrt(sum(y*y for y in b))
    return 0.0 if da == 0 or db == 0 else max(0.0, min(1.0, num/(da*db)))

def difficulty_penalty(user: UserProfileIn, cand: Candidate) -> float:
    # crude: more steps or presence of tags could increase difficulty. You can refine later.
    if user.difficulty == "beginner":
        if "advanced" in cand.tags: return 0.2
        if user.maxSteps and "steps:" in " ".join(cand.tags):
            # If you encode steps count as a tag later, parse it here
            pass
    return 0.0

def taste_score(user: UserProfileIn, cand: Candidate, userTasteEmbedding: Optional[List[float]] = None) -> float:
    liked = set([x.lower() for x in user.likedCuisines])
    rc    = set([x.lower() for x in cand.cuisines])
    tasteCuisine = len(liked & rc) / (len(liked) if liked else 1)
    emb = 0.0
    if userTasteEmbedding and cand.embedding:
        emb = cosine(userTasteEmbedding, cand.embedding)
    return clamp01(0.6 * tasteCuisine + 0.4 * emb)

def pantry_score(pantry: Set[str], cand: Candidate) -> Tuple[float, int, List[Dict[str,str]]]:
    covered = 0
    miss    = []
    for ing in cand.ingredients:
        # treat id as canonical; fallback to name match (simple)
        in_pantry = (ing.id in pantry) or (ing.name and ing.name.lower() in pantry)
        if in_pantry and ing.priceCents:
            covered += ing.priceCents
        elif not in_pantry and ing.priceCents:
            miss.append({"ingredientId": ing.id or "", "name": ing.name, "estimatedCostCents": str(ing.priceCents)})
    score = covered / max(1, cand.estimatedCostCents)
    return clamp01(score), covered, miss

def price_fit(cost: int, target: Optional[int]) -> float:
    if not target: return 0.6
    if cost <= target: return 1.0
    return clamp01(1.0 - (cost - target) / max(target, 1))

def time_fit(minutes: int, minutesMax: Optional[int]) -> float:
    if not minutesMax: return 0.6
    if minutes <= minutesMax: return 1.0
    return clamp01(1.0 - (minutes - minutesMax) / max(minutesMax, 1))

def violated_diet(user: UserProfileIn, cand: Candidate) -> bool:
    # Phase-1: if user is vegan/vegetarian and tags contain 'meat' tokens, etc. (stub)
    # You can wire exact flags later when normalization exists.
    d = set([x.lower() for x in user.diet])
    if "vegan" in d and ("chicken" in cand.title.lower() or "pork" in cand.title.lower()):
        return True
    if "vegetarian" in d and ("chicken" in cand.title.lower() or "pork" in cand.title.lower()):
        return True
    return False

def build_weights(user: UserProfileIn) -> Dict[str, float]:
    w_price  = 0.2 + 0.6 * clamp01(user.priceSensitivity)
    w_pantry = 0.2 + 0.3 * clamp01(user.priceSensitivity)
    w_time   = 0.3 if (user.minutesMax is not None and user.minutesMax <= 30) else 0.15
    w_taste  = 0.6
    s = w_price + w_pantry + w_time + w_taste
    return { "taste": w_taste/s, "price": w_price/s, "time": w_time/s, "pantry": w_pantry/s }

def explain(user: UserProfileIn, cand: Candidate, subscores: Dict[str,float], missing: List[Dict[str,str]]) -> List[Dict[str,str]]:
    # pick reasons aligned with the big-3
    reasons: List[Dict[str,str]] = []
    # Taste
    reasons.append({ "key":"taste", "label": f"{', '.join(cand.cuisines) or 'flavors'} you like" })
    # Time
    if user.minutesMax is not None:
        reasons.append({ "key":"time", "label": f"{cand.minutesTotal} min" })
    # Price (only if they care)
    if user.priceSensitivity >= 0.5:
        reasons.append({ "key":"price", "label": f"${cand.estimatedCostCents/100:.2f} est." })
    # Pantry / missing
    if missing:
        # show only the most salient missing item
        m0 = missing[0]
        reasons.append({ "key":"missing", "label": f"missing {m0['name']} (+${int(m0['estimatedCostCents'])/100:.2f})" })
    return reasons[:3]

def score_one(user: UserProfileIn, pantryIds: Set[str], budgetDayCents: Optional[int], cand: Candidate,
              userTasteEmbedding: Optional[List[float]] = None) -> RankItem | None:
    if violated_diet(user, cand):
        return None
    w = build_weights(user)

    panScore, covered, missing = pantry_score(pantryIds, cand)
    pfit  = price_fit(cand.estimatedCostCents, budgetDayCents)
    tfit  = time_fit(cand.minutesTotal, user.minutesMax)
    taste = taste_score(user, cand, userTasteEmbedding)

    penalty = 0.0
    # dislikes simple penalty
    low = [x.lower() for x in user.dislikedIngredients]
    if any(ing.name and ing.name.lower() in low for ing in cand.ingredients):
        penalty += 0.3
    penalty += difficulty_penalty(user, cand)

    base = w["taste"]*taste + w["price"]*pfit + w["time"]*tfit + w["pantry"]*panScore
    score01 = clamp01(base - penalty)
    reasons = explain(user, cand, {"taste":taste,"price":pfit,"time":tfit,"pantry":panScore}, missing)
    return RankItem(
        recipeId=cand.id,
        title=cand.title,
        score01=score01,
        score10=round(10*score01, 1),
        estimatedCostCents=cand.estimatedCostCents,
        minutesTotal=cand.minutesTotal,
        reasons=reasons,
        missing=missing
    )

@router.post("/rank", response_model=List[RankItem])
def rank(req: RankRequest):
    pantry = set([x.lower() for x in req.pantry])  # accept IDs or names; we lowercase to match names fallback
    out: List[RankItem] = []
    for c in req.candidates:
        r = score_one(req.user, pantry, req.budgetDayCents, c, None)
        if r: out.append(r)
    out.sort(key=lambda x: x.score01, reverse=True)
    return out[:max(1, req.k)]

@router.post("/plan/suggest", response_model=PlanOut)
def plan(req: PlanSuggestRequest):
    # 1) score all candidates
    ranked = rank(RankRequest(user=req.user, pantry=req.pantry, budgetDayCents=int(req.budgetWeekCents/max(1,req.days)),
                              k=len(req.candidates), candidates=req.candidates))
    # 2) greedy pick 1 per day within budget, with light diversity
    picked: List[RankItem] = []
    total = 0
    seen_cuisines: Dict[str, int] = {}
    for r in ranked:
        # diversity: avoid over-using same cuisine
        # find candidate cuisines from r.title in req.candidates (cheap lookup)
        cand = next((c for c in req.candidates if c.id == r.recipeId), None)
        cuisines = [x.lower() for x in (cand.cuisines if cand else [])]
        penalty = sum(seen_cuisines.get(ci,0) for ci in cuisines)
        # budget gate (soft)
        if total + r.estimatedCostCents > req.budgetWeekCents and len(picked) < req.days:
            continue
        picked.append(r)
        total += r.estimatedCostCents
        for ci in cuisines: seen_cuisines[ci] = seen_cuisines.get(ci,0) + 1
        if len(picked) >= req.days: break

    # 3) build PlanOut
    days: List[PlanDay] = []
    for i in range(req.days):
        item = picked[i] if i < len(picked) else None
        days.append(PlanDay(index=i, dinner=item))
    return PlanOut(startDate=req.startDate, days=days, estimatedTotalCents=total)
