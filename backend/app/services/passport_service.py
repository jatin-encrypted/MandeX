"""
passport_service.py — Commerce Passport CRUD + structural validation.
No LLM calls — validation is purely schema/range-based because the
merchant is the authoritative data source (Mode 1 onboarding).
"""
import json
import uuid
from datetime import datetime
from sqlalchemy.orm import Session

from app.db.models import ProductDB, MerchantRulesDB, CommercePassportDB, MerchantDB
from app.schemas.passport import (
    Product,
    MerchantRules,
    CommercePassport,
    PassportCreateRequest,
    ValidationError,
    ValidationResult,
)
from app.services import audit_service


# ---------------------------------------------------------------------------
# Validation — structural + range only, no ML
# ---------------------------------------------------------------------------

def validate_passport(products: list[Product], rules: MerchantRules) -> ValidationResult:
    errors: list[ValidationError] = []

    if not products:
        errors.append(ValidationError(field="products", message="Catalog must have at least one product."))

    for p in products:
        if p.price_inr <= 0:
            errors.append(ValidationError(field=f"products[{p.id}].price_inr", message="Price must be > 0."))
        if p.stock < 0:
            errors.append(ValidationError(field=f"products[{p.id}].stock", message="Stock cannot be negative."))
        if not p.name.strip():
            errors.append(ValidationError(field=f"products[{p.id}].name", message="Product name cannot be empty."))
        if not p.category.strip():
            errors.append(ValidationError(field=f"products[{p.id}].category", message="Category cannot be empty."))

        # Range check: if min_margin is 20%, warn if price seems below a plausible cost
        # We can only flag if price is suspiciously low (< ₹1) — merchant sets actual margins.
        if p.price_inr < 1:
            errors.append(ValidationError(field=f"products[{p.id}].price_inr", message="Price below ₹1 is invalid."))

    if rules.max_ai_discount_pct < 0 or rules.max_ai_discount_pct > 100:
        errors.append(ValidationError(field="rules.max_ai_discount_pct", message="Discount % must be 0–100."))
    if rules.min_margin_pct < 0 or rules.min_margin_pct > 100:
        errors.append(ValidationError(field="rules.min_margin_pct", message="Margin % must be 0–100."))
    if rules.require_approval_above_inr < 0:
        errors.append(ValidationError(field="rules.require_approval_above_inr", message="Approval threshold must be ≥ 0."))

    return ValidationResult(valid=len(errors) == 0, errors=errors)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_or_update_passport(
    db: Session,
    merchant_id: str,
    request: PassportCreateRequest,
) -> tuple[CommercePassport, ValidationResult]:
    """Create / overwrite a merchant's passport in draft state."""
    products = [
        Product(id=str(uuid.uuid4()), **p.model_dump())
        for p in request.products
    ]
    validation = validate_passport(products, request.rules)
    if not validation.valid:
        return None, validation  # caller raises 422

    # Upsert products (clear old ones first)
    db.query(ProductDB).filter(ProductDB.merchant_id == merchant_id).delete()
    for p in products:
        db.add(ProductDB(
            id=p.id,
            merchant_id=merchant_id,
            name=p.name,
            price_inr=p.price_inr,
            stock=p.stock,
            category=p.category,
            description=p.description,
            return_policy=p.return_policy,
        ))

    # Upsert rules
    existing_rules = db.query(MerchantRulesDB).filter(MerchantRulesDB.merchant_id == merchant_id).first()
    if existing_rules:
        existing_rules.max_ai_discount_pct = request.rules.max_ai_discount_pct
        existing_rules.min_margin_pct = request.rules.min_margin_pct
        existing_rules.ai_upsell_enabled = request.rules.ai_upsell_enabled
        existing_rules.preferred_categories = json.dumps(request.rules.preferred_categories)
        existing_rules.require_approval_above_inr = request.rules.require_approval_above_inr
    else:
        db.add(MerchantRulesDB(
            merchant_id=merchant_id,
            max_ai_discount_pct=request.rules.max_ai_discount_pct,
            min_margin_pct=request.rules.min_margin_pct,
            ai_upsell_enabled=request.rules.ai_upsell_enabled,
            preferred_categories=json.dumps(request.rules.preferred_categories),
            require_approval_above_inr=request.rules.require_approval_above_inr,
        ))

    # Upsert passport record (draft)
    existing_passport = db.query(CommercePassportDB).filter(
        CommercePassportDB.merchant_id == merchant_id
    ).first()
    if existing_passport:
        existing_passport.status = "draft"
        existing_passport.activated_at = None
    else:
        db.add(CommercePassportDB(
            merchant_id=merchant_id,
            status="draft",
            created_at=datetime.utcnow(),
        ))

    db.commit()
    return get_passport(db, merchant_id), validation


def activate_passport(db: Session, merchant_id: str) -> CommercePassport | None:
    """Mark a passport ACTIVE. Logs the activation event."""
    passport_db = db.query(CommercePassportDB).filter(
        CommercePassportDB.merchant_id == merchant_id
    ).first()
    if not passport_db:
        return None

    passport_db.status = "active"
    passport_db.activated_at = datetime.utcnow()
    db.commit()

    audit_service.log(
        db,
        event_type="passport_activated",
        merchant_id=merchant_id,
        payload={"activated_at": passport_db.activated_at.isoformat()},
    )

    return get_passport(db, merchant_id)


def get_passport(db: Session, merchant_id: str) -> CommercePassport | None:
    passport_db = db.query(CommercePassportDB).filter(
        CommercePassportDB.merchant_id == merchant_id
    ).first()
    if not passport_db:
        return None

    products = _get_products(db, merchant_id)
    rules = _get_rules(db, merchant_id)
    return CommercePassport(
        merchant_id=merchant_id,
        products=products,
        rules=rules,
        status=passport_db.status,
        created_at=passport_db.created_at,
        activated_at=passport_db.activated_at,
    )


def get_active_passport(db: Session, merchant_id: str) -> CommercePassport | None:
    passport = get_passport(db, merchant_id)
    if passport and passport.status == "active":
        return passport
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_products(db: Session, merchant_id: str) -> list[Product]:
    rows = db.query(ProductDB).filter(ProductDB.merchant_id == merchant_id).all()
    return [
        Product(
            id=r.id, name=r.name, price_inr=r.price_inr, stock=r.stock,
            category=r.category, description=r.description, return_policy=r.return_policy,
        )
        for r in rows
    ]


def _get_rules(db: Session, merchant_id: str) -> MerchantRules:
    row = db.query(MerchantRulesDB).filter(MerchantRulesDB.merchant_id == merchant_id).first()
    if not row:
        return MerchantRules()
    return MerchantRules(
        max_ai_discount_pct=row.max_ai_discount_pct,
        min_margin_pct=row.min_margin_pct,
        ai_upsell_enabled=row.ai_upsell_enabled,
        preferred_categories=row.get_preferred_categories(),
        require_approval_above_inr=row.require_approval_above_inr,
    )
