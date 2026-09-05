"""
merchant.py — REST endpoints for the merchant dashboard.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import MerchantDB, AuditLogDB
from app.schemas.passport import (
    PassportCreateRequest,
    CommercePassport,
    ValidationResult,
)
from app.schemas.mandate import MandateCreateRequest, Mandate
from app.services import passport_service, mandate_service, audit_service

router = APIRouter(prefix="/merchant", tags=["Merchant"])


# ---------------------------------------------------------------------------
# Merchant registration (called after Firebase Auth creates the user)
# ---------------------------------------------------------------------------

class MerchantRegisterReq:
    pass


from pydantic import BaseModel


class MerchantRegisterReq(BaseModel):
    merchant_id: str  # Firebase UID
    email: str
    display_name: str


@router.post("/register", response_model=dict)
def register_merchant(req: MerchantRegisterReq, db: Session = Depends(get_db)):
    existing = db.query(MerchantDB).filter(MerchantDB.merchant_id == req.merchant_id).first()
    if existing:
        return {"merchant_id": existing.merchant_id, "already_exists": True}
    db.add(MerchantDB(
        merchant_id=req.merchant_id,
        email=req.email,
        display_name=req.display_name,
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    return {"merchant_id": req.merchant_id, "already_exists": False}


# ---------------------------------------------------------------------------
# Commerce Passport CRUD
# ---------------------------------------------------------------------------

@router.post("/{merchant_id}/passport", response_model=CommercePassport)
def create_passport(
    merchant_id: str,
    req: PassportCreateRequest,
    db: Session = Depends(get_db),
):
    passport, validation = passport_service.create_or_update_passport(db, merchant_id, req)
    if not validation.valid:
        raise HTTPException(422, detail=[e.model_dump() for e in validation.errors])
    return passport


@router.get("/{merchant_id}/passport", response_model=CommercePassport)
def get_passport(merchant_id: str, db: Session = Depends(get_db)):
    passport = passport_service.get_passport(db, merchant_id)
    if not passport:
        raise HTTPException(404, f"No passport found for merchant {merchant_id}.")
    return passport


@router.post("/{merchant_id}/passport/activate", response_model=CommercePassport)
def activate_passport(merchant_id: str, db: Session = Depends(get_db)):
    passport = passport_service.activate_passport(db, merchant_id)
    if not passport:
        raise HTTPException(404, f"No passport found for merchant {merchant_id}.")
    return passport


# ---------------------------------------------------------------------------
# Mandate management (demo: merchants can seed mandates for buyers)
# ---------------------------------------------------------------------------

@router.post("/{merchant_id}/mandates", response_model=Mandate)
def create_mandate(
    merchant_id: str,
    req: MandateCreateRequest,
    db: Session = Depends(get_db),
):
    return mandate_service.create_mandate(db, req)


@router.get("/{merchant_id}/mandates/{mandate_id}", response_model=Mandate)
def get_mandate(merchant_id: str, mandate_id: str, db: Session = Depends(get_db)):
    mandate = mandate_service.get_mandate(db, mandate_id)
    if not mandate:
        raise HTTPException(404, f"Mandate {mandate_id} not found.")
    return mandate


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class AuditEntryOut(BaseModel):
    log_id: str
    event_type: str
    merchant_id: str
    cart_id: str | None
    payload: dict
    timestamp: datetime


@router.get("/{merchant_id}/audit", response_model=list[AuditEntryOut])
def get_audit_log(merchant_id: str, db: Session = Depends(get_db)):
    entries = audit_service.get_entries_for_merchant(db, merchant_id)
    return [
        AuditEntryOut(
            log_id=e.log_id,
            event_type=e.event_type,
            merchant_id=e.merchant_id,
            cart_id=e.cart_id,
            payload=json.loads(e.payload),
            timestamp=e.timestamp,
        )
        for e in entries
    ]
