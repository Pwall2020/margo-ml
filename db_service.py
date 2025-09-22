from typing import Dict, Optional
from sqlalchemy import create_engine, Column, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
import uuid
import sqlalchemy as sa

Base = declarative_base()

class Recipe(Base):
    __tablename__ = "recipes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(Text, nullable=False)
    instructions = Column(Text, nullable=True)
    prep_mins = Column(Integer, nullable=True)
    cook_mins = Column(Integer, nullable=True)
    servings = Column(Integer, nullable=False, default=4)
    tips = Column(Text, nullable=True)
    calories = Column(Integer, nullable=True)
    details = Column(JSONB, nullable=False)  # For remaining fields like ingredients, tags, embedding
    embedding = Column(Vector(384), nullable=True)
    source = Column(Text, nullable=True)
    source_id = Column(sa.BigInteger, nullable=True)
    generated_by_user_id = Column(PG_UUID(as_uuid=True), nullable=True)

engine = create_engine('postgresql://margo:margo@localhost:5432/margo')  # Your creds
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

def store_recipe(
    recipe: Dict,
    user_id: Optional[str] = None,
    source: str = "margo-ml",
    source_id: Optional[int] = None,
    session_factory=Session
) -> str:
    # Convert IngredientLine objects to dicts for JSON serialization
    recipe_copy = recipe.copy()
    if "ingredients" in recipe_copy and isinstance(recipe_copy["ingredients"], list):
        recipe_copy["ingredients"] = [ing.model_dump() for ing in recipe_copy["ingredients"]]

    with session_factory() as session:
        obj = Recipe(
            title=recipe_copy.get("title", ""),
            instructions=recipe_copy.get("instructions", ""),
            prep_mins=recipe_copy.get("prepMinutes"),
            cook_mins=recipe_copy.get("cookMinutes"),
            servings=recipe_copy.get("servings", 4),
            tips=recipe_copy.get("tips", ""),
            calories=recipe_copy.get("calories"),
            details=recipe_copy,  # Now JSON-serializable
            embedding=recipe_copy.get("embedding"),
            source=source,
            source_id=source_id,
            generated_by_user_id=uuid.UUID(user_id) if user_id else None,
        )
        session.add(obj)
        session.commit()
        return str(obj.id)