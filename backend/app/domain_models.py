from pydantic import BaseModel, Field, HttpUrl


class FlightCard(BaseModel):
    airline: str
    price: float = Field(ge=0)
    direct: bool
    departure_time: str
    arrival_time: str


class ProductCard(BaseModel):
    title: str
    price: float = Field(ge=0)
    rating: float = Field(ge=0, le=5)
    url: HttpUrl


class GmailDraft(BaseModel):
    recipient: str
    subject: str
    body: str


class WhatsAppMessage(BaseModel):
    contact_name: str
    message_text: str
