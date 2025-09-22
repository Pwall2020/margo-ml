import torch
import requests
import re
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
from transformers import pipeline
from models import IngredientLine, GenerateRequest, UserPreferences
from catalogs import estimated_cost

device = "cuda:0" if torch.cuda.is_available() else "cpu"
generator = pipeline('text-generation', model='gpt2-medium', device=0 if torch.cuda.is_available() else -1)
embedder = SentenceTransformer('all-MiniLM-L6-v2', device=device)


def parse_generated_text(gen_text: str, pantry_str: str) -> Dict:
    print(f"Raw LLM output: {gen_text}")  # Debug: Print full output
    lines = gen_text.split('\n')
    title = lines[0].strip() if lines else "Generated Recipe"
    ingredients_start = next((i for i, line in enumerate(lines) if 'ingredients' in line.lower()), -1)
    instructions_start = next((i for i, line in enumerate(lines) if 'instructions' in line.lower()), -1)
    tips_start = next((i for i, line in enumerate(lines) if 'tips' in line.lower()), -1)

    ingredients = []
    # Parse ingredients with fallback for missing sections
    if ingredients_start != -1:
        start_idx = ingredients_start + 1
        end_idx = min(instructions_start, tips_start) if -1 not in (instructions_start, tips_start) else len(lines)
        for line in lines[start_idx:end_idx]:
            if line.strip():
                match = re.match(r'(\d*\.?\d+(?:/\d+)?|\w+)\s*(\w+)?\s*(.*)', line.strip())
                if match:
                    qty_str, unit, name = match.groups()
                    try:
                        qty = float(qty_str) if qty_str.replace('.', '', 1).isdigit() else {
                            'half': 0.5,
                            'quarter': 0.25,
                            'one': 1.0
                        }.get(qty_str.lower(), None) if '/' not in qty_str else eval(qty_str)
                    except:
                        qty = None
                    ingredients.append(IngredientLine(name=name.strip() or line.strip(), qty=qty, unit=unit))
        # Fallback to pantry items if no ingredients parsed
        if not ingredients:
            for item in pantry_str.split(', '):
                ingredients.append(IngredientLine(name=item.strip(), qty=1.0, unit=""))

    instructions = '\n'.join(lines[instructions_start + 1: tips_start if tips_start != -1 else len(
        lines)]) if instructions_start != -1 else "Follow standard steps."
    tips = '\n'.join(lines[tips_start + 1:]) if tips_start != -1 else "Adjust spices to taste."

    return {'title': title, 'ingredients': ingredients, 'instructions': instructions, 'tips': tips}


def generate_ml_structured(req: GenerateRequest) -> Dict:
    diet_str = ', '.join(req.diet) or 'any'
    tech_str = ', '.join(req.techniques) or 'simple'
    cuisine_str = ', '.join(req.cuisine) or 'varied'
    pantry_str = ', '.join(req.pantry) or 'basic staples'
    prompt = (
        f"Create a unique {diet_str} recipe for {req.servings} servings. "
        f"Use {tech_str} methods, {cuisine_str} style. Budget: under ${req.budgetCents / 100:.2f}. "
        f"Time: {req.minutes} minutes total. Include pantry: {pantry_str}. "
        "Format: Title on first line. Then 'Ingredients:' with at least 2-3 specific items (e.g., 2 cups rice, 1 lb tofu, 1/2 tsp salt). Then 'Instructions:' with 4-6 numbered steps. Then 'Tips:'."
    )

    gen = generator(prompt, max_new_tokens=500, num_return_sequences=1, temperature=0.7)[0]['generated_text']
    parsed = parse_generated_text(gen, pantry_str)  # Pass pantry_str

    recipe_text = parsed['title'] + ' ' + parsed['instructions']
    embedding = embedder.encode(recipe_text, batch_size=32).tolist()

    cost = estimated_cost(req.servings, [i.dict() for i in parsed['ingredients']]) if parsed['ingredients'] else 0
    prep = max(5, req.minutes // 3)
    cook = req.minutes - prep
    calories = get_nutrition(parsed['ingredients']) if parsed['ingredients'] else None

    return {
        'id': None,
        'title': parsed['title'],
        'servings': req.servings,
        'prepMinutes': prep,
        'cookMinutes': cook,
        'calories': calories,
        'imageUrl': None,
        'tags': req.techniques + req.diet + req.cuisine,
        'instructions': parsed['instructions'],
        'tips': parsed['tips'],
        'ingredients': parsed['ingredients'],
        'estimatedCostCents': cost,
        'embedding': embedding
    }


def get_nutrition(ingredients: List[IngredientLine]) -> Optional[int]:
    if not ingredients:
        return None  # Avoid empty query
    query = ' '.join(f"{i.qty or 1} {i.unit or ''} {i.name}" for i in ingredients)
    print(f"QUERY: {query}")  # Debug query sent to Edamam
    app_id = "02e8c544"
    app_key = "08577906b34375ff41062ec9b8982f52"
    resp = requests.get(f"https://api.edamam.com/api/nutrition-data?app_id={app_id}&app_key={app_key}&ingr={query}")
    print(f"RESPONSE: {resp.json()}")  # Debug full response
    return resp.json().get('calories', None) if resp.ok else None


def get_user_embedding(prefs: UserPreferences) -> Dict:
    prefs_text = ' '.join(filter(None, [
        ', '.join(prefs.dietaryTags),
        ', '.join(prefs.favoriteCuisines),
        ', '.join(f"no {item}" for item in prefs.dislikedItems) if prefs.dislikedItems else 'no dislikes',
        f"{prefs.maxPrepMinutes or 30} minutes",
        f"{prefs.householdSize or 2} servings",
        f"budget {prefs.weeklyBudgetCents or 1200} cents",
        prefs.tasteProfile or '',
        prefs.primaryStore or '',
        ' '.join(f"{k}:{v}" for k, v in (prefs.extra or {}).items())
    ]))
    embedding = embedder.encode(prefs_text, batch_size=32).tolist()
    return {"embedding": embedding}