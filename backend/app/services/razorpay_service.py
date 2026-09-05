"""
razorpay_service.py — Razorpay Orders API (TEST MODE only).

Idempotency: a repeated checkout call with the same idempotency_key
returns the existing RazorpayOrderDB row — Razorpay is NOT called again.
"""
import json
import razorpay
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import RazorpayOrderDB
from app.services import audit_service


def _client():
    s = get_settings()
    return razorpay.Client(auth=(s.razorpay_key_id, s.razorpay_key_secret))


def create_and_capture_order(
    db: Session,
    cart_id: str,
    merchant_id: str,
    total_inr: float,
    idempotency_key: str,
) -> dict:
    """
    Creates a Razorpay test-mode order.
    Returns {"razorpay_order_id": str, "status": str, "amount_paise": int}.
    Idempotent: same idempotency_key returns existing row without calling Razorpay again.
    On any failure, logs payment_failed and re-raises so the caller can return
    payment_status="failed" in the DecisionReceipt.
    """
    # Idempotency check — don't call Razorpay twice for the same key
    existing = db.query(RazorpayOrderDB).filter(
        RazorpayOrderDB.idempotency_key == idempotency_key
    ).first()
    if existing:
        return {
            "razorpay_order_id": existing.razorpay_order_id,
            "status": existing.status,
            "amount_paise": existing.amount_paise,
            "idempotent": True,
        }

    amount_paise = int(round(total_inr * 100))

    audit_service.log(
        db,
        event_type="payment_attempted",
        merchant_id=merchant_id,
        cart_id=cart_id,
        payload={
            "amount_inr": total_inr,
            "amount_paise": amount_paise,
            "idempotency_key": idempotency_key,
        },
    )

    try:
        client = _client()
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": cart_id[:40],  # Razorpay receipt max 40 chars
            "payment_capture": 1,
            "notes": {"idempotency_key": idempotency_key},
        })
        razorpay_order_id = order["id"]
    except Exception as exc:
        audit_service.log(
            db,
            event_type="razorpay_payment_failed",
            merchant_id=merchant_id,
            cart_id=cart_id,
            payload={"error": str(exc), "idempotency_key": idempotency_key},
        )
        raise

    # Persist the order for idempotency
    db.add(RazorpayOrderDB(
        idempotency_key=idempotency_key,
        razorpay_order_id=razorpay_order_id,
        cart_id=cart_id,
        amount_paise=amount_paise,
        status="created",
    ))
    db.commit()

    audit_service.log(
        db,
        event_type="razorpay_order_created",
        merchant_id=merchant_id,
        cart_id=cart_id,
        payload={
            "razorpay_order_id": razorpay_order_id,
            "amount_paise": amount_paise,
            "idempotency_key": idempotency_key,
        },
    )

    return {
        "razorpay_order_id": razorpay_order_id,
        "status": "created",
        "amount_paise": amount_paise,
        "idempotent": False,
    }
