from pydantic import BaseModel, Field
from typing import List

from app.domain_models import FlightCard, ProductCard

class SemanticPageModel(BaseModel):
    """Unified semantic payload returned from Extractor V2."""
    flights: List[FlightCard] = Field(default_factory=list)
    products: List[ProductCard] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list, description="Common form identifiers found")
