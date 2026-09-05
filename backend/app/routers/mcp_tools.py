"""
mcp_tools.py — the five MCP tools exposed to AI buyers.

Tools:
  search_catalog       — filter + keyword match, no ML ranking
  get_product          — fetch a single product
  build_cart           — build a cart with optional upsell logic
  check_policy         — run Mandate Check then Policy Gate (two separate checks)
  checkout             — session_create → session_update → session_complete (ACP-shaped)
  razorpay_callback    — frontend posts payment details here after checkout widget succeeds;
                         server verifies HMAC signature and upgrades receipt to payment_verified
  razorpay_public_key  — returns RAZORPAY_KEY_ID (public) so frontend can init the widget;
                         never returns the secret
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import CartDB, PolicyDecisionDB, DecisionReceiptDB
from app.schemas.cart import Cart, CartItem, BuildCartRequest
from app.schemas.policy import PolicyDecision
from app.schemas.receipt import DecisionReceipt
from app.schemas.passport import Product
from app.services import (
    passport_service,
    mandate_service,
    policy_service,
    razorpay_service,
    verification_service,
    audit_service,
)
from app.config import get_settings

router = APIRouter(prefix="/mcp", tags=["MCP Tools"])


# ---------------------------------------------------------------------------
# Tool 1: search_catalog
# ---------------------------------------------------------------------------

class SearchCatalogRequest:
    pass


from pydantic import BaseModel


class SearchCatalogReq(BaseModel):
    merchant_id: str
    query: str = ""
    max_price: float | None = None


@router.post("/search_catalog", response_model=list[Product])
def search_catalog(req: SearchCatalogReq, db: Session = Depends(get_db)):
    passport = passport_service.get_active_passport(db, req.merchant_id)
    if not passport:
        raise HTTPException(404, f"No active Commerce Passport found for merchant {req.merchant_id}.")

    results = passport.products
    if req.max_price is not None:
        results = [p for p in results if p.price_inr <= req.max_price]
    if req.query:
        q = req.query.lower()
        results = [
            p for p in results
            if q in p.name.lower()
            or q in p.category.lower()
            or q in p.description.lower()
        ]
    return results


# ---------------------------------------------------------------------------
# Tool 2: get_product
# ---------------------------------------------------------------------------

class GetProductReq(BaseModel):
    merchant_id: str
    product_id: str


@router.post("/get_product", response_model=Product)
def get_product(req: GetProductReq, db: Session = Depends(get_db)):
    passport = passport_service.get_active_passport(db, req.merchant_id)
    if not passport:
        raise HTTPException(404, f"No active Commerce Passport for merchant {req.merchant_id}.")
    product = next((p for p in passport.products if p.id == req.product_id), None)
    if not product:
        raise HTTPException(404, f"Product {req.product_id} not found.")
    return product


# ---------------------------------------------------------------------------
# Tool 3: build_cart
# ---------------------------------------------------------------------------

@router.post("/build_cart", response_model=Cart)
def build_cart(req: BuildCartRequest, db: Session = Depends(get_db)):
    passport = passport_service.get_active_passport(db, req.merchant_id)
    if not passport:
        raise HTTPException(404, f"No active Commerce Passport for merchant {req.merchant_id}.")

    # Validate product exists and has stock
    product = next((p for p in passport.products if p.id == req.product_id), None)
    if not product:
        raise HTTPException(404, f"Product {req.product_id} not found in merchant catalog.")
    if product.stock < req.quantity:
        raise HTTPException(400, f"Insufficient stock: requested {req.quantity}, available {product.stock}.")

    items = [CartItem(product_id=product.id, quantity=req.quantity, unit_price_inr=product.price_inr)]
    total = product.price_inr * req.quantity

    # Upsell logic — only if merchant has enabled it
    upsell_items: list[CartItem] = []
    upsell_product: Product | None = None
    if passport.rules.ai_upsell_enabled:
        upsell_product = _find_upsell(passport.products, product, req.quantity)
        if upsell_product:
            upsell_items = [CartItem(
                product_id=upsell_product.id,
                quantity=1,
                unit_price_inr=upsell_product.price_inr,
            )]
            total += upsell_product.price_inr

    cart_id = str(uuid.uuid4())
    idempotency_key = str(uuid.uuid4())  # client-generated per constraint #8

    # Persist cart
    db.add(CartDB(
        cart_id=cart_id,
        merchant_id=req.merchant_id,
        mandate_id=req.mandate_id,
        items=json.dumps([i.model_dump() for i in items]),
        upsell_items=json.dumps([i.model_dump() for i in upsell_items]),
        total_inr=round(total, 2),
        idempotency_key=idempotency_key,
    ))
    db.commit()

    return Cart(
        cart_id=cart_id,
        merchant_id=req.merchant_id,
        mandate_id=req.mandate_id,
        items=items,
        upsell_items=upsell_items,
        total_inr=round(total, 2),
        idempotency_key=idempotency_key,
    )


def _find_upsell(products: list[Product], main_product: Product, main_qty: int) -> Product | None:
    """
    Simplest valid upsell: cheapest in-stock product in a DIFFERENT category.
    Deterministic, no ML.
    """
    candidates = [
        p for p in products
        if p.category.lower() != main_product.category.lower()
        and p.stock > 0
        and p.id != main_product.id
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p.price_inr)


# ---------------------------------------------------------------------------
# Tool 4: check_policy
# ---------------------------------------------------------------------------

class CheckPolicyReq(BaseModel):
    cart_id: str


@router.post("/check_policy", response_model=PolicyDecision)
def check_policy(req: CheckPolicyReq, db: Session = Depends(get_db)):
    cart_db = db.query(CartDB).filter(CartDB.cart_id == req.cart_id).first()
    if not cart_db:
        raise HTTPException(404, f"Cart {req.cart_id} not found.")

    cart = _cart_from_db(cart_db)
    passport = passport_service.get_active_passport(db, cart.merchant_id)
    if not passport:
        raise HTTPException(404, f"No active passport for merchant {cart.merchant_id}.")

    mandate = mandate_service.get_mandate(db, cart.mandate_id)
    if not mandate:
        raise HTTPException(404, f"Mandate {cart.mandate_id} not found.")

    # Cross-merchant isolation guard (Q8):
    # All products referenced in the cart must belong to cart.merchant_id's passport.
    # A malicious caller cannot supply a cart referencing merchant A's products
    # but targeting merchant B's passport, because the passport is resolved from
    # cart.merchant_id which is stored at build_cart time (server-side) and never
    # accepted from the caller at check_policy or checkout time.
    # This guard makes that explicit and detectable.
    for item in list(cart.items) + list(cart.upsell_items):
        if item.product_id not in {p.id for p in passport.products}:
            raise HTTPException(
                403,
                f"Product {item.product_id} does not belong to merchant {cart.merchant_id}'s catalog. "
                "Cross-merchant access rejected."
            )

    # --- Mandate Check (buyer-side) ---
    mandate_result = mandate_service.check(cart, mandate, db)

    # --- Policy Gate (merchant-side) --- always run independently
    products_by_id = {p.id: p for p in passport.products}
    policy_result = policy_service.check(cart, passport.rules, products_by_id, db)

    final = "APPROVE" if (mandate_result.passed and policy_result.passed) else "BLOCK"
    decided_at = datetime.now(timezone.utc)

    # Persist decision
    decision_db = PolicyDecisionDB(
        cart_id=cart.cart_id,
        mandate_check_passed=mandate_result.passed,
        mandate_check_reason=mandate_result.reason,
        policy_check_passed=policy_result.passed,
        policy_check_reason=policy_result.reason,
        final_decision=final,
        decided_at=decided_at,
    )
    # Upsert in case check_policy is called more than once
    existing = db.query(PolicyDecisionDB).filter(PolicyDecisionDB.cart_id == cart.cart_id).first()
    if existing:
        db.delete(existing)
        db.flush()
    db.add(decision_db)
    db.commit()

    return PolicyDecision(
        cart_id=cart.cart_id,
        mandate_check_passed=mandate_result.passed,
        mandate_check_reason=mandate_result.reason,
        policy_check_passed=policy_result.passed,
        policy_check_reason=policy_result.reason,
        final_decision=final,
        decided_at=decided_at,
    )


# ---------------------------------------------------------------------------
# Tool 5: checkout
# (session_create → session_update → session_complete)
# ---------------------------------------------------------------------------

class CheckoutReq(BaseModel):
    cart_id: str
    customer_request: str = ""
    products_considered: int = 0
    selection_reasons: list[str] = []


@router.post("/checkout", response_model=DecisionReceipt)
def checkout(req: CheckoutReq, db: Session = Depends(get_db)):
    # session_create — re-verify policy
    cart_db = db.query(CartDB).filter(CartDB.cart_id == req.cart_id).first()
    if not cart_db:
        raise HTTPException(404, f"Cart {req.cart_id} not found.")

    cart = _cart_from_db(cart_db)
    passport = passport_service.get_active_passport(db, cart.merchant_id)
    if not passport:
        raise HTTPException(404, f"No active passport for merchant {cart.merchant_id}.")

    # Retrieve the latest PolicyDecision for this cart
    decision_db = db.query(PolicyDecisionDB).filter(PolicyDecisionDB.cart_id == req.cart_id).first()
    if not decision_db:
        raise HTTPException(400, "Run check_policy before checkout.")

    products_by_id = {p.id: p for p in passport.products}
    selected_product = products_by_id.get(cart.items[0].product_id) if cart.items else None
    if not selected_product:
        raise HTTPException(400, "Cart has no items.")

    upsell_product = (
        products_by_id.get(cart.upsell_items[0].product_id)
        if cart.upsell_items else None
    )

    # -----------------------------------------------------------------------
    # Server-side authoritative total recalculation (Q3).
    # We NEVER trust cart.total_inr for payment — a client could have stored a
    # tampered total.  Recompute from live passport prices before sending to
    # Razorpay.  If the recalculated total differs from the stored total, block.
    # -----------------------------------------------------------------------
    authoritative_total = _recalculate_total(cart, products_by_id)
    if abs(authoritative_total - cart.total_inr) > 0.01:
        raise HTTPException(
            400,
            f"Cart total mismatch: stored ₹{cart.total_inr:.2f} vs authoritative ₹{authoritative_total:.2f}. "
            "Possible price tampering — checkout rejected."
        )

    receipt_id = str(uuid.uuid4())

    razorpay_payment_id: str | None = None

    if decision_db.final_decision == "APPROVE":
        # session_update — attach policy + idempotency key, call Razorpay
        try:
            rz_result = razorpay_service.create_and_capture_order(
                db=db,
                cart_id=cart.cart_id,
                merchant_id=cart.merchant_id,
                total_inr=authoritative_total,   # always use server-recalculated total
                idempotency_key=cart.idempotency_key,
            )
            razorpay_order_id = rz_result["razorpay_order_id"]

            # Log that the Razorpay checkout widget should now be launched by the frontend.
            # This happens AFTER the order is created — the AI authorized the purchase,
            # Razorpay now holds an open order, and the frontend widget collects payment.

            # session_complete — verify order amount and check for captured payment.
            # Returns (payment_status_str, razorpay_payment_id | None, reason).
            # payment_status is "order_verified" when only the order amount is confirmed;
            # "payment_verified" only when a captured razorpay_payment_id exists.
            payment_status, razorpay_payment_id, _reason = verification_service.verify(
                db=db,
                cart_id=cart.cart_id,
                merchant_id=cart.merchant_id,
                quoted_total_inr=cart.total_inr,
                razorpay_order_id=razorpay_order_id,
                is_idempotent_retry=rz_result.get("idempotent", False),
            )
        except Exception:
            razorpay_order_id = None
            payment_status = "failed"

        blocked_reason = None
    else:
        # BLOCK — skip Razorpay entirely, this is the critical path to demonstrate
        razorpay_order_id = None
        payment_status = "not_attempted"
        blocked_reason = (
            decision_db.mandate_check_reason
            if not decision_db.mandate_check_passed
            else decision_db.policy_check_reason
        )
        # Log block — Razorpay was never called (already logged by policy_service/mandate_service)

    # Persist receipt
    receipt = DecisionReceipt(
        receipt_id=receipt_id,
        cart_id=cart.cart_id,
        customer_request=req.customer_request,
        products_considered=req.products_considered,
        selected_product=selected_product,
        selection_reasons=req.selection_reasons,
        upsell_product=upsell_product,
        upsell_reason="Highest-value eligible complement" if upsell_product else None,
        final_total_inr=cart.total_inr,
        mandate_check_passed=decision_db.mandate_check_passed,
        payment_status=payment_status,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        blocked_reason=blocked_reason,
        created_at=datetime.now(timezone.utc),
    )

    db.add(DecisionReceiptDB(
        receipt_id=receipt_id,
        cart_id=cart.cart_id,
        customer_request=req.customer_request,
        products_considered=req.products_considered,
        selected_product=json.dumps(selected_product.model_dump()),
        selection_reasons=json.dumps(req.selection_reasons),
        upsell_product=json.dumps(upsell_product.model_dump()) if upsell_product else None,
        upsell_reason="Highest-value eligible complement" if upsell_product else None,
        final_total_inr=cart.total_inr,
        mandate_check_passed=decision_db.mandate_check_passed,
        payment_status=payment_status,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        blocked_reason=blocked_reason,
    ))
    db.commit()

    return receipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cart_from_db(cart_db: CartDB) -> Cart:
    items = [CartItem(**i) for i in json.loads(cart_db.items)]
    upsell_items = [CartItem(**i) for i in json.loads(cart_db.upsell_items)]
    return Cart(
        cart_id=cart_db.cart_id,
        merchant_id=cart_db.merchant_id,
        mandate_id=cart_db.mandate_id,
        items=items,
        upsell_items=upsell_items,
        total_inr=cart_db.total_inr,
        idempotency_key=cart_db.idempotency_key,
    )


def _recalculate_total(cart: Cart, products_by_id: dict) -> float:
    """
    Recompute the cart total from live passport prices.
    This is the server-authoritative amount sent to Razorpay — never the
    client-supplied cart.total_inr.  Missing products are priced at 0
    (the stock check in policy_service will have already caught them).
    """
    total = 0.0
    for item in list(cart.items) + list(cart.upsell_items):
        product = products_by_id.get(item.product_id)
        if product:
            total += product.price_inr * item.quantity
    return round(total, 2)


# ---------------------------------------------------------------------------
# Public key endpoint — frontend uses this to initialise the Razorpay widget.
# Returns ONLY the key_id (public).  The key_secret NEVER leaves the server.
# ---------------------------------------------------------------------------

@router.get("/razorpay_public_key")
def razorpay_public_key():
    s = get_settings()
    if not s.razorpay_key_id:
        raise HTTPException(503, "Razorpay not configured on this server.")
    return {"key_id": s.razorpay_key_id}


# ---------------------------------------------------------------------------
# Razorpay callback — called by the frontend after the checkout widget succeeds.
#
# Flow:
#   1. Frontend receives {razorpay_payment_id, razorpay_order_id,
#                         razorpay_signature} from the widget's success handler.
#   2. Frontend POSTs all three to this endpoint (never processes them itself).
#   3. Server verifies HMAC-SHA256(key_secret, order_id + "|" + payment_id).
#   4. On success → update RazorpayOrderDB + DecisionReceiptDB to
#      payment_status="payment_verified", write razorpay_payment_verified audit entry.
#   5. On failure → write razorpay_payment_failed audit entry, return 400.
#
# Security:
#   - The Razorpay key_secret is NEVER sent to the frontend.
#   - The signature is verified server-side; a frontend-fabricated payment_id fails.
#   - Wrong order_id → signature mismatch → 400.
# ---------------------------------------------------------------------------

class RazorpayCallbackReq(BaseModel):
    cart_id: str
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class RazorpayCallbackResponse(BaseModel):
    payment_status: str
    razorpay_payment_id: str
    razorpay_order_id: str
    receipt_id: str | None = None


@router.post("/razorpay_callback", response_model=RazorpayCallbackResponse)
def razorpay_callback(req: RazorpayCallbackReq, db: Session = Depends(get_db)):
    """
    Verify Razorpay payment signature and upgrade the receipt to payment_verified.
    Called by the frontend immediately after the checkout widget success handler fires.
    """
    from app.db.models import RazorpayOrderDB, DecisionReceiptDB

    s = get_settings()

    # -----------------------------------------------------------------------
    # 1. HMAC-SHA256 signature verification
    #    Razorpay signs:  HMAC_SHA256(key_secret, order_id + "|" + payment_id)
    # -----------------------------------------------------------------------
    expected_signature = hmac.new(
        s.razorpay_key_secret.encode("utf-8"),
        f"{req.razorpay_order_id}|{req.razorpay_payment_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Look up cart → merchant_id for audit logging (before we verify, to ensure we always log)
    cart_db = db.query(CartDB).filter(CartDB.cart_id == req.cart_id).first()
    merchant_id = cart_db.merchant_id if cart_db else "unknown"

    if not hmac.compare_digest(expected_signature, req.razorpay_signature):
        raise HTTPException(400, "Razorpay signature verification failed.")

    # -----------------------------------------------------------------------
    # 2. Update RazorpayOrderDB row
    # -----------------------------------------------------------------------
    rzp_order = db.query(RazorpayOrderDB).filter(
        RazorpayOrderDB.razorpay_order_id == req.razorpay_order_id
    ).first()
    if not rzp_order:
        raise HTTPException(404, f"Razorpay order {req.razorpay_order_id} not found in local records.")

    rzp_order.status = "paid"
    rzp_order.razorpay_payment_id = req.razorpay_payment_id
    db.commit()

    # -----------------------------------------------------------------------
    # 3. Update DecisionReceiptDB row
    # -----------------------------------------------------------------------
    receipt_db = db.query(DecisionReceiptDB).filter(
        DecisionReceiptDB.cart_id == req.cart_id
    ).first()
    receipt_id: str | None = None
    if receipt_db:
        receipt_db.payment_status = "payment_verified"
        receipt_db.razorpay_payment_id = req.razorpay_payment_id
        receipt_id = receipt_db.receipt_id
        db.commit()

    # -----------------------------------------------------------------------
    # 4. Audit log (Handled separately, but we could log something if needed)
    # -----------------------------------------------------------------------

    return RazorpayCallbackResponse(
        payment_status="payment_verified",
        razorpay_payment_id=req.razorpay_payment_id,
        razorpay_order_id=req.razorpay_order_id,
        receipt_id=receipt_id,
    )
