from pydantic import BaseModel, Field
from typing import List, Optional, Dict

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
    diet: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    techniques: List[str] = Field(default_factory=list)
    cuisine: List[str] = Field(default_factory=list)
    seed: Optional[int] = None

class UserPreferences(BaseModel):
    userId: str
    householdSize: Optional[int] = None
    weeklyBudgetCents: Optional[int] = None
    maxPrepMinutes: Optional[int] = None
    dietaryTags: List[str] = Field(default_factory=list)
    dislikedItems: List[str] = Field(default_factory=list)
    favoriteCuisines: List[str] = Field(default_factory=list)
    tasteProfile: Optional[str] = None
    primaryStore: Optional[str] = None
    extra: Optional[Dict] = None

class RecipeOut(BaseModel):
    id: Optional[str] = None  # Changed from Optional[int] to Optional[str] for UUID
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
    embedding: Optional[List[float]] = None

class BulkRequest(BaseModel):
    count: int = 100
    servings: Optional[int] = None
    servingsOptions: Optional[List[int]] = None
    minutes: int = 30
    budgetCents: int = 1500
    diet: List[str] = []
    avoid: List[str] = []
    techniques: List[str] = []
    cuisine: List[str] = []
    seed: Optional[int] = None