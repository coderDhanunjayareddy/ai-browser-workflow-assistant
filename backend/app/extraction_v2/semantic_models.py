from pydantic import BaseModel, Field
from typing import Optional, List

class FlightCard(BaseModel):
    """Structured flight information card from travel sites."""
    airline: str = Field(description="Airline name or code")
    price: float = Field(description="Total price of the flight")
    departure_time: str = Field(description="Departure time string")
    arrival_time: str = Field(description="Arrival time string")
    stops: int = Field(default=0, description="Number of layovers/stops")
    duration: Optional[str] = None
    element_id: Optional[str] = None

class ProductCard(BaseModel):
    """Structured product details card from e-commerce sites."""
    title: str = Field(description="Product listing name")
    price: float = Field(description="Product price")
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    url: Optional[str] = None
    element_id: Optional[str] = None

class SemanticPageModel(BaseModel):
    """Unified semantic payload returned from Extractor V2."""
    flights: List[FlightCard] = Field(default_factory=list)
    products: List[ProductCard] = Field(default_factory=list)
    forms: List[str] = Field(default_factory=list, description="Common form identifiers found")
