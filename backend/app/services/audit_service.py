"""
audit_service.py — append-only audit log.
Every state-changing path calls audit_service.log() before returning.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Literal
from sqlalchemy.orm import Session

from app.db.models import AuditLogDB

EventType = Literal[
    "passport_activated",
    "mandate_checked",
    "policy_decided",
    "payment_attempted",
    "payment_verified",
    "payment_mismatch",
    "payment_failed",
    # Razorpay-specific granular events
    "razorpay_order_created",
    "razorpay_checkout_started",
    "razorpay_payment_verified",
    "razorpay_payment_failed",
]


def log(
    db: Session,
    event_type: EventType,
    merchant_id: str,
    payload: dict,
    cart_id: str | None = None,
) -> AuditLogDB:
    entry = AuditLogDB(
        log_id=str(uuid.uuid4()),
        event_type=event_type,
        merchant_id=merchant_id,
        cart_id=cart_id,
        payload=json.dumps(payload),
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_entries_for_merchant(db: Session, merchant_id: str) -> list[AuditLogDB]:
    return (
        db.query(AuditLogDB)
        .filter(AuditLogDB.merchant_id == merchant_id)
        .order_by(AuditLogDB.timestamp.desc())
        .all()
    )
