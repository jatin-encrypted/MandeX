"""
verification_service.py — post-order verification.

Razorpay Orders API flow (important context):
  client.order.create()  →  order status = "created"
                             NO money has moved.  The buyer must still submit
                             card / UPI details through the Razorpay checkout
                             widget.  Only then does status become "paid" and a
                             Payment object with a razorpay_payment_id exists.

This means our backend-only happy path can at most confirm:
  "we created an order and Razorpay agrees the amount is correct"
  → payment_status = "order_verified"

If a payment was actually captured (e.g. via Razorpay test-mode auto-capture or
a payment completed through the checkout widget), order.payments() will return a
Payment object with status "captured".  In that case we return:
  → payment_status = "payment_verified"  +  razorpay_payment_id

The caller (checkout tool) is responsible for using the correct status string.
Never call the result "payment_verified" unless a razorpay_payment_id exists.
"""
import razorpay
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import RazorpayOrderDB
from app.services import audit_service

# Return type: (payment_status_str, razorpay_payment_id_or_None, reason_str)
VerifyResult = tuple[str, str | None, str]


def verify(
    db: Session,
    cart_id: str,
    merchant_id: str,
    quoted_total_inr: float,
    razorpay_order_id: str,
    is_idempotent_retry: bool = False,
) -> VerifyResult:
    """
    Returns (payment_status, razorpay_payment_id | None, reason).

    payment_status is one of:
      "order_verified"   — order amount confirmed; no payment captured yet
      "payment_verified" — payment captured, razorpay_payment_id present
      "failed"           — Razorpay API error or amount mismatch
    """
    expected_paise = int(round(quoted_total_inr * 100))

    if is_idempotent_retry:
        # Fast path on retries: the first call already ran the full check.
        # Use the local record to avoid a redundant API call.
        local = db.query(RazorpayOrderDB).filter(
            RazorpayOrderDB.razorpay_order_id == razorpay_order_id
        ).first()
        if local and abs(local.amount_paise - expected_paise) <= 1:
            prior_status = (
                "payment_verified" if local.razorpay_payment_id
                else "order_verified"
            )
            audit_service.log(
                db,
                event_type="payment_verified",
                merchant_id=merchant_id,
                cart_id=cart_id,
                payload={
                    "razorpay_order_id": razorpay_order_id,
                    "razorpay_payment_id": local.razorpay_payment_id,
                    "expected_paise": expected_paise,
                    "actual_paise": local.amount_paise,
                    "source": "local_record_idempotent_retry",
                    "payment_status": prior_status,
                },
            )
            return prior_status, local.razorpay_payment_id, "Idempotent retry — verified from local record."

    # ----------------------------------------------------------------
    # Step 1 — fetch the order from Razorpay and verify amount
    # ----------------------------------------------------------------
    try:
        s = get_settings()
        client = razorpay.Client(auth=(s.razorpay_key_id, s.razorpay_key_secret))
        order = client.order.fetch(razorpay_order_id)
    except Exception as exc:
        audit_service.log(
            db,
            event_type="payment_failed",
            merchant_id=merchant_id,
            cart_id=cart_id,
            payload={
                "error": f"order.fetch failed: {exc}",
                "razorpay_order_id": razorpay_order_id,
            },
        )
        return "failed", None, f"Could not fetch Razorpay order: {exc}"

    actual_paise = int(order.get("amount_due", order.get("amount", 0)))
    if abs(actual_paise - expected_paise) > 1:
        audit_service.log(
            db,
            event_type="payment_mismatch",
            merchant_id=merchant_id,
            cart_id=cart_id,
            payload={
                "razorpay_order_id": razorpay_order_id,
                "expected_paise": expected_paise,
                "actual_paise": actual_paise,
            },
        )
        return (
            "failed",
            None,
            f"Amount mismatch: quoted ₹{quoted_total_inr:.2f} ({expected_paise}p) "
            f"but Razorpay recorded {actual_paise}p.",
        )

    # Amount is correct.  Now check whether a payment was actually captured.
    order_status = order.get("status", "created")  # "created" | "attempted" | "paid"

    # ----------------------------------------------------------------
    # Step 2 — look for a captured payment on this order
    # ----------------------------------------------------------------
    razorpay_payment_id: str | None = None

    if order_status == "paid":
        # Order is paid — fetch the payment list to get the payment ID.
        try:
            payments_resp = client.order.payments(razorpay_order_id)
            captured_payments = [
                p for p in payments_resp.get("items", [])
                if p.get("status") == "captured"
            ]
            if captured_payments:
                razorpay_payment_id = captured_payments[0]["id"]
        except Exception as exc:
            # Payment list fetch failing does not invalidate the order amount check.
            # We degrade to order_verified rather than failing the whole checkout.
            audit_service.log(
                db,
                event_type="payment_failed",
                merchant_id=merchant_id,
                cart_id=cart_id,
                payload={
                    "error": f"order.payments() fetch failed: {exc}",
                    "razorpay_order_id": razorpay_order_id,
                    "note": "order amount was confirmed; degrading to order_verified",
                },
            )

    # ----------------------------------------------------------------
    # Step 3 — update local RazorpayOrderDB row with fetched state
    # ----------------------------------------------------------------
    local = db.query(RazorpayOrderDB).filter(
        RazorpayOrderDB.razorpay_order_id == razorpay_order_id
    ).first()
    if local:
        local.status = order_status
        if razorpay_payment_id:
            local.razorpay_payment_id = razorpay_payment_id
        db.commit()

    # ----------------------------------------------------------------
    # Step 4 — decide the final payment_status string
    # ----------------------------------------------------------------
    if razorpay_payment_id:
        final_status = "payment_verified"
        reason = f"Payment captured. Razorpay payment ID: {razorpay_payment_id}."
    else:
        final_status = "order_verified"
        reason = (
            f"Order amount confirmed by Razorpay (order status: {order_status!r}). "
            "No payment captured yet — buyer must complete checkout widget to transfer funds."
        )

    audit_service.log(
        db,
        event_type="payment_verified",
        merchant_id=merchant_id,
        cart_id=cart_id,
        payload={
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "order_status": order_status,
            "expected_paise": expected_paise,
            "actual_paise": actual_paise,
            "payment_status": final_status,
            "source": "razorpay_api",
        },
    )
    return final_status, razorpay_payment_id, reason
