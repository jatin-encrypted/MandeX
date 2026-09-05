from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class PolicyDecision(BaseModel):
    cart_id: str
    mandate_check_passed: bool
    mandate_check_reason: str
    policy_check_passed: bool
    policy_check_reason: str
    final_decision: Literal["APPROVE", "BLOCK"]
    decided_at: datetime
