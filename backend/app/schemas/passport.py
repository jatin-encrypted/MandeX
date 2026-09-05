from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


class Product(BaseModel):
    id: str
    name: str
    price_inr: float
    stock: int
    category: str
    description: str
    return_policy: str


class MerchantRules(BaseModel):
    max_ai_discount_pct: float = 10.0
    min_margin_pct: float = 20.0
    ai_upsell_enabled: bool = True
    preferred_categories: list[str] = []
    require_approval_above_inr: float = 10000.0


class CommercePassport(BaseModel):
    merchant_id: str
    products: list[Product]
    rules: MerchantRules
    status: Literal["draft", "active"]
    created_at: datetime
    activated_at: datetime | None = None


# --- Request bodies ---

class ProductCreate(BaseModel):
    name: str
    price_inr: float
    stock: int
    category: str
    description: str
    return_policy: str


class PassportCreateRequest(BaseModel):
    products: list[ProductCreate]
    rules: MerchantRules


class PassportActivateRequest(BaseModel):
    merchant_id: str


# --- Validation result ---

class ValidationError(BaseModel):
    field: str
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = []
