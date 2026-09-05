"""
seed_demo.py — seeds one demo merchant with a realistic sports/footwear catalog
and creates a demo mandate (₹6,000 limit) to enable the required demo scenarios.

Run ONCE after first-time setup:
  cd backend
  PYTHONPATH=. python seed_demo.py

This script creates:
  - A merchant record (no Firebase auth needed for seeding)
  - A Commerce Passport with 8 products across 3 categories
  - An ACTIVE passport status
  - A demo mandate for buyer "demo-buyer" with ₹6,000 limit

After running, note the MERCHANT_ID and MANDATE_ID printed at the end.
Paste them into frontend/.env as VITE_DEMO_MERCHANT_ID and VITE_DEMO_MANDATE_ID.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timezone, timedelta
from app.db.session import SessionLocal, engine
from app.db import models
from app.schemas.passport import PassportCreateRequest, ProductCreate, MerchantRules
from app.schemas.mandate import MandateCreateRequest
from app.services import passport_service, mandate_service
from app.db.models import MerchantDB, MandateDB, CommercePassportDB

# Create tables
models.Base.metadata.create_all(bind=engine)

MERCHANT_ID = "demo-merchant-001"
MERCHANT_EMAIL = "demo@mandex.ai"
MERCHANT_NAME = "Velocity Sports"

PRODUCTS = [
    ProductCreate(
        name="Velocity Pro Running Shoes",
        price_inr=5499.0,
        stock=25,
        category="shoes",
        description="Lightweight carbon-plate running shoes for road racing. Responsive cushioning.",
        return_policy="30 days",
    ),
    ProductCreate(
        name="TrailBlazer All-Terrain Shoes",
        price_inr=4299.0,
        stock=18,
        category="shoes",
        description="Rugged trail running shoes with aggressive lug outsole. Waterproof upper.",
        return_policy="30 days",
    ),
    ProductCreate(
        name="SprintX Track Spikes",
        price_inr=8999.0,
        stock=10,
        category="shoes",
        description="Competition track spikes for sprinters. Removable 6mm ceramic spikes.",
        return_policy="No returns on competition footwear",
    ),
    ProductCreate(
        name="EasyRun Foam Trainers",
        price_inr=2799.0,
        stock=40,
        category="shoes",
        description="Daily trainer with full-length foam cushioning. Ideal for easy runs.",
        return_policy="30 days",
    ),
    ProductCreate(
        name="Pro Running Socks (3-pack)",
        price_inr=499.0,
        stock=100,
        category="accessories",
        description="Moisture-wicking compression socks with arch support. Fits sizes 6–10.",
        return_policy="15 days",
    ),
    ProductCreate(
        name="Hydration Vest 5L",
        price_inr=2199.0,
        stock=15,
        category="accessories",
        description="Trail running vest with 5L capacity, two soft flasks included.",
        return_policy="30 days",
    ),
    ProductCreate(
        name="Performance Dry-Fit Tee",
        price_inr=899.0,
        stock=50,
        category="apparel",
        description="Ultra-lightweight running tee with reflective strips.",
        return_policy="30 days",
    ),
    ProductCreate(
        name="Wind-Resistant Running Jacket",
        price_inr=3499.0,
        stock=20,
        category="apparel",
        description="Packable windproof jacket with rear ventilation. 80g.",
        return_policy="30 days",
    ),
]

RULES = MerchantRules(
    max_ai_discount_pct=10.0,
    min_margin_pct=20.0,
    ai_upsell_enabled=True,
    preferred_categories=["shoes", "accessories"],
    require_approval_above_inr=9000.0,
)

def seed():
    db = SessionLocal()
    try:
        # Create merchant record
        existing = db.query(MerchantDB).filter(MerchantDB.merchant_id == MERCHANT_ID).first()
        if not existing:
            db.add(MerchantDB(
                merchant_id=MERCHANT_ID,
                email=MERCHANT_EMAIL,
                display_name=MERCHANT_NAME,
                created_at=datetime.now(timezone.utc),
            ))
            db.commit()
            print(f"Created merchant: {MERCHANT_ID}")
        else:
            print(f"Merchant already exists: {MERCHANT_ID}")

        # Create/update passport
        req = PassportCreateRequest(products=PRODUCTS, rules=RULES)
        passport, validation = passport_service.create_or_update_passport(db, MERCHANT_ID, req)
        if not validation.valid:
            print("Validation errors:")
            for e in validation.errors:
                print(f"  {e.field}: {e.message}")
            sys.exit(1)
        print(f"Passport saved (draft) with {len(passport.products)} products.")

        # Activate
        passport = passport_service.activate_passport(db, MERCHANT_ID)
        print(f"Passport activated: {passport.status}")

        # Re-sign all existing demo mandates so stored signatures always match
        # the current MANDATE_SIGNING_SECRET.  This is idempotent — safe to re-run.
        import json as _json
        from app.schemas.mandate import Mandate as MandateSchema
        existing_mandates = db.query(MandateDB).filter(MandateDB.buyer_id == "demo-buyer").all()
        for m in existing_mandates:
            m_schema = MandateSchema(
                mandate_id=m.mandate_id, buyer_id=m.buyer_id,
                max_amount_inr=m.max_amount_inr,
                allowed_categories=_json.loads(m.allowed_categories),
                expires_at=m.expires_at, issued_at=m.issued_at, signature="",
            )
            m.signature = mandate_service.sign(m_schema)
        db.commit()
        if existing_mandates:
            print(f"Re-signed {len(existing_mandates)} existing mandate(s) with current secret.")

        # Create demo mandate — expires in 90 days, well past any demo date
        mandate_req = MandateCreateRequest(
            buyer_id="demo-buyer",
            max_amount_inr=6000.0,
            allowed_categories=[],  # empty = all categories allowed
            expires_at=datetime.now(timezone.utc) + timedelta(days=90),
        )
        mandate = mandate_service.create_mandate(db, mandate_req)
        print(f"\nMandate created: {mandate.mandate_id}")
        print(f"  buyer_id:       {mandate.buyer_id}")
        print(f"  max_amount_inr: ₹{mandate.max_amount_inr:,.2f}")
        print(f"  expires_at:     {mandate.expires_at.isoformat()}")

        print("\n" + "=" * 60)
        print("DEMO SEED COMPLETE")
        print("=" * 60)
        print(f"MERCHANT_ID = {MERCHANT_ID}")
        print(f"MANDATE_ID  = {mandate.mandate_id}")
        print()
        print("Add these to frontend/.env:")
        print(f"  VITE_DEMO_MERCHANT_ID={MERCHANT_ID}")
        print(f"  VITE_DEMO_MANDATE_ID={mandate.mandate_id}")
        print()
        print("Demo scenarios ready:")
        print('  Happy path: "Find me running shoes under ₹6,000"')
        print('  Blocked:    "Buy the ₹8,999 version instead"')
        print('             (SprintX Track Spikes exceed mandate limit)')

    finally:
        db.close()


if __name__ == "__main__":
    seed()
