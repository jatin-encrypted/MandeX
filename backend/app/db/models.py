import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON
from app.db.session import Base


class MerchantDB(Base):
    __tablename__ = "merchants"

    merchant_id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ProductDB(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, index=True)
    merchant_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    price_inr = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    return_policy = Column(String, nullable=False)


class MerchantRulesDB(Base):
    __tablename__ = "merchant_rules"

    merchant_id = Column(String, primary_key=True)
    max_ai_discount_pct = Column(Float, nullable=False, default=10.0)
    min_margin_pct = Column(Float, nullable=False, default=20.0)
    ai_upsell_enabled = Column(Boolean, nullable=False, default=True)
    preferred_categories = Column(Text, nullable=False, default="[]")  # JSON string
    require_approval_above_inr = Column(Float, nullable=False, default=10000.0)

    def get_preferred_categories(self) -> list[str]:
        return json.loads(self.preferred_categories)


class CommercePassportDB(Base):
    __tablename__ = "commerce_passports"

    merchant_id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="draft")  # draft | active
    created_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)


class MandateDB(Base):
    __tablename__ = "mandates"

    mandate_id = Column(String, primary_key=True, index=True)
    buyer_id = Column(String, nullable=False, index=True)
    max_amount_inr = Column(Float, nullable=False)
    allowed_categories = Column(Text, nullable=False, default="[]")  # JSON string
    expires_at = Column(DateTime, nullable=False)
    issued_at = Column(DateTime, default=datetime.utcnow)
    signature = Column(String, nullable=False)

    def get_allowed_categories(self) -> list[str]:
        return json.loads(self.allowed_categories)


class CartDB(Base):
    __tablename__ = "carts"

    cart_id = Column(String, primary_key=True, index=True)
    merchant_id = Column(String, nullable=False, index=True)
    mandate_id = Column(String, nullable=False)
    items = Column(Text, nullable=False, default="[]")  # JSON string
    upsell_items = Column(Text, nullable=False, default="[]")  # JSON string
    total_inr = Column(Float, nullable=False)
    idempotency_key = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PolicyDecisionDB(Base):
    __tablename__ = "policy_decisions"

    cart_id = Column(String, primary_key=True)
    mandate_check_passed = Column(Boolean, nullable=False)
    mandate_check_reason = Column(String, nullable=False)
    policy_check_passed = Column(Boolean, nullable=False)
    policy_check_reason = Column(String, nullable=False)
    final_decision = Column(String, nullable=False)  # APPROVE | BLOCK
    decided_at = Column(DateTime, default=datetime.utcnow)


class DecisionReceiptDB(Base):
    __tablename__ = "decision_receipts"

    receipt_id = Column(String, primary_key=True, index=True)
    cart_id = Column(String, unique=True, nullable=False, index=True)
    customer_request = Column(Text, nullable=False)
    products_considered = Column(Integer, nullable=False, default=0)
    selected_product = Column(Text, nullable=False)  # JSON
    selection_reasons = Column(Text, nullable=False, default="[]")  # JSON
    upsell_product = Column(Text, nullable=True)  # JSON or NULL
    upsell_reason = Column(Text, nullable=True)
    final_total_inr = Column(Float, nullable=False)
    mandate_check_passed = Column(Boolean, nullable=False)
    # payment_status values:
    #   "not_attempted"  — BLOCK path, Razorpay never called
    #   "order_verified" — order created + Razorpay confirms correct amount,
    #                      but NO payment has been captured yet (normal for Orders API)
    #   "payment_verified" — a payment was captured and confirmed via payments API
    #   "failed"         — Razorpay call failed or amount mismatch
    payment_status = Column(String, nullable=False, default="not_attempted")
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)   # populated only if payment captured
    blocked_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLogDB(Base):
    __tablename__ = "audit_log"

    log_id = Column(String, primary_key=True, index=True)
    event_type = Column(String, nullable=False)
    merchant_id = Column(String, nullable=False, index=True)
    cart_id = Column(String, nullable=True, index=True)
    payload = Column(Text, nullable=False, default="{}")  # JSON
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class RazorpayOrderDB(Base):
    __tablename__ = "razorpay_orders"

    idempotency_key = Column(String, primary_key=True, index=True)
    razorpay_order_id = Column(String, unique=True, nullable=False)
    cart_id = Column(String, nullable=False)
    amount_paise = Column(Integer, nullable=False)
    # Razorpay order status: "created" | "attempted" | "paid"
    status = Column(String, nullable=False, default="created")
    # Populated only once a payment is captured on this order
    razorpay_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
