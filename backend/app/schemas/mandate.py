from datetime import datetime
from pydantic import BaseModel


class Mandate(BaseModel):
    mandate_id: str
    buyer_id: str
    max_amount_inr: float
    allowed_categories: list[str]
    expires_at: datetime
    issued_at: datetime
    signature: str


class MandateCreateRequest(BaseModel):
    buyer_id: str
    max_amount_inr: float
    allowed_categories: list[str]
    expires_at: datetime


class MandateCheckResult(BaseModel):
    passed: bool
    reason: str
