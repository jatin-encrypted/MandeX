from datetime import datetime
from typing import Literal
from pydantic import BaseModel
from app.schemas.passport import Product


class DecisionReceipt(BaseModel):
    receipt_id: str
    cart_id: str
    customer_request: str
    products_considered: int
    selected_product: Product
    selection_reasons: list[str]
    upsell_product: Product | None = None
    upsell_reason: str | None = None
    final_total_inr: float
    mandate_check_passed: bool
    # payment_status semantics:
    #   "not_attempted"  — BLOCK path, Razorpay was never called
    #   "order_verified" — Razorpay order created and amount confirmed via order.fetch();
    #                      the checkout UI must still collect card details to capture payment
    #   "payment_verified" — a razorpay_payment_id was found on the order, amount confirmed
    #   "failed"         — Razorpay call failed or amount mismatch
    payment_status: Literal["not_attempted", "order_verified", "payment_verified", "failed"]
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None  # present only when payment_status == "payment_verified"
    blocked_reason: str | None = None
    created_at: datetime | None = None
