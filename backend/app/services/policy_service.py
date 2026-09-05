"""
policy_service.py — deterministic merchant-side Policy Gate.
Rules engine is purely if/else over merchant-configured thresholds.
No ML, no scoring — this is explainable by design.

min_margin_pct vs max_ai_discount_pct — both are enforced:

  max_ai_discount_pct (e.g. 10):
    The AI buyer is not allowed to apply a discount greater than this percentage
    off the list price.  Enforced as a floor:
      min_allowed_price = list_price × (1 - max_ai_discount_pct / 100)
    Any unit_price_inr below that floor is rejected.
    Example: list ₹5,000, max_discount=10% → floor ₹4,500.
             unit_price ₹4,000 → BLOCK.

  min_margin_pct (e.g. 20):
    The merchant's stated minimum gross margin.  Enforced as a separate floor:
      margin_floor_price = list_price × (1 - min_margin_pct / 100)
    This prevents the AI from pricing below the merchant's cost basis even if
    the discount cap alone would permit it.
    Example: list ₹5,000, min_margin=20% → floor ₹4,000.
             unit_price ₹3,500 → BLOCK (even if max_discount=50% would allow it).

  In practice the tighter constraint wins.  Both are checked independently.

require_approval_above_inr:
    This is a HARD BLOCK in the current implementation — there is no human
    approval queue.  A cart total above this threshold is rejected immediately
    with a clear explanation.  Rename if you add an async approval workflow.
"""
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import ProductDB
from app.schemas.cart import Cart, CartItem
from app.schemas.passport import MerchantRules
from app.services import audit_service


class PolicyCheckResult:
    def __init__(self, passed: bool, reason: str):
        self.passed = passed
        self.reason = reason


def check(
    cart: Cart,
    rules: MerchantRules,
    products_by_id: dict,  # product_id → Product
    db: Session,
) -> PolicyCheckResult:
    """
    Checks in order — stops at first failure:
    1. Stock availability for each item.
    2. max_ai_discount_pct floor — unit_price >= list × (1 - max_ai_discount_pct/100).
    3. min_margin_pct floor    — unit_price >= list × (1 - min_margin_pct/100).
    4. require_approval_above_inr — hard block if cart total exceeds threshold.

    All checks produce a logged reason.
    """
    all_items = list(cart.items) + list(cart.upsell_items)

    # 1. Stock
    for item in all_items:
        product = products_by_id.get(item.product_id)
        if product is None:
            result = PolicyCheckResult(False, f"Product {item.product_id} not found in merchant catalog.")
            _log(db, cart, result)
            return result
        if product.stock < item.quantity:
            result = PolicyCheckResult(
                False,
                f"Insufficient stock for '{product.name}': requested {item.quantity}, available {product.stock}.",
            )
            _log(db, cart, result)
            return result

    # 2. max_ai_discount_pct floor
    for item in all_items:
        product = products_by_id.get(item.product_id)
        if product is None:
            continue
        discount_floor = product.price_inr * (1 - rules.max_ai_discount_pct / 100)
        if item.unit_price_inr < discount_floor - 0.005:  # 0.5 paise float tolerance
            result = PolicyCheckResult(
                False,
                (
                    f"Price ₹{item.unit_price_inr:.2f} for '{product.name}' is below the "
                    f"AI discount cap floor ₹{discount_floor:.2f} "
                    f"(max {rules.max_ai_discount_pct}% discount from list price ₹{product.price_inr:.2f})."
                ),
            )
            _log(db, cart, result)
            return result

    # 3. min_margin_pct floor
    #    This is a separate check from the discount cap above.  Both must pass.
    for item in all_items:
        product = products_by_id.get(item.product_id)
        if product is None:
            continue
        margin_floor = product.price_inr * (1 - rules.min_margin_pct / 100)
        if item.unit_price_inr < margin_floor - 0.005:
            result = PolicyCheckResult(
                False,
                (
                    f"Price ₹{item.unit_price_inr:.2f} for '{product.name}' is below the "
                    f"minimum margin floor ₹{margin_floor:.2f} "
                    f"({rules.min_margin_pct}% margin on list price ₹{product.price_inr:.2f})."
                ),
            )
            _log(db, cart, result)
            return result

    # 4. Approval threshold — hard block (no async approval queue exists)
    if cart.total_inr > rules.require_approval_above_inr:
        result = PolicyCheckResult(
            False,
            (
                f"Cart total ₹{cart.total_inr:.2f} exceeds the merchant's autonomous AI limit "
                f"of ₹{rules.require_approval_above_inr:.2f}. "
                f"This is a hard block — no payment is attempted."
            ),
        )
        _log(db, cart, result)
        return result

    result = PolicyCheckResult(True, "All policy checks passed: stock, discount cap, margin floor, and autonomous limit.")
    _log(db, cart, result)
    return result


def _log(db: Session, cart: Cart, result: PolicyCheckResult):
    audit_service.log(
        db,
        event_type="policy_decided",
        merchant_id=cart.merchant_id,
        cart_id=cart.cart_id,
        payload={
            "passed": result.passed,
            "reason": result.reason,
            "cart_total_inr": cart.total_inr,
        },
    )
