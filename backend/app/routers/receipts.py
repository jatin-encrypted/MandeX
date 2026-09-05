"""
receipts.py — Decision Receipt retrieval endpoints.
"""
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import DecisionReceiptDB
from app.schemas.receipt import DecisionReceipt
from app.schemas.passport import Product

router = APIRouter(prefix="/receipts", tags=["Receipts"])


@router.get("/{receipt_id}", response_model=DecisionReceipt)
def get_receipt(receipt_id: str, db: Session = Depends(get_db)):
    row = db.query(DecisionReceiptDB).filter(DecisionReceiptDB.receipt_id == receipt_id).first()
    if not row:
        raise HTTPException(404, f"Receipt {receipt_id} not found.")
    return _row_to_receipt(row)


@router.get("/by-cart/{cart_id}", response_model=DecisionReceipt)
def get_receipt_by_cart(cart_id: str, db: Session = Depends(get_db)):
    row = db.query(DecisionReceiptDB).filter(DecisionReceiptDB.cart_id == cart_id).first()
    if not row:
        raise HTTPException(404, f"No receipt found for cart {cart_id}.")
    return _row_to_receipt(row)


def _row_to_receipt(row: DecisionReceiptDB) -> DecisionReceipt:
    selected = Product(**json.loads(row.selected_product))
    upsell = Product(**json.loads(row.upsell_product)) if row.upsell_product else None
    return DecisionReceipt(
        receipt_id=row.receipt_id,
        cart_id=row.cart_id,
        customer_request=row.customer_request,
        products_considered=row.products_considered,
        selected_product=selected,
        selection_reasons=json.loads(row.selection_reasons),
        upsell_product=upsell,
        upsell_reason=row.upsell_reason,
        final_total_inr=row.final_total_inr,
        mandate_check_passed=row.mandate_check_passed,
        payment_status=row.payment_status,
        razorpay_order_id=row.razorpay_order_id,
        razorpay_payment_id=row.razorpay_payment_id,
        blocked_reason=row.blocked_reason,
        created_at=row.created_at,
    )
