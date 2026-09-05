"""
test_policy_service.py — priority tests for policy_service.check().
"""
import pytest
from unittest.mock import MagicMock

from app.schemas.cart import Cart, CartItem
from app.schemas.passport import Product, MerchantRules
from app.services import policy_service


def _make_rules(
    max_ai_discount_pct: float = 10.0,
    min_margin_pct: float = 20.0,
    ai_upsell_enabled: bool = True,
    require_approval_above_inr: float = 10000.0,
) -> MerchantRules:
    return MerchantRules(
        max_ai_discount_pct=max_ai_discount_pct,
        min_margin_pct=min_margin_pct,
        ai_upsell_enabled=ai_upsell_enabled,
        preferred_categories=[],
        require_approval_above_inr=require_approval_above_inr,
    )


def _make_product(price: float = 5000, stock: int = 10, pid: str = "p1") -> Product:
    return Product(
        id=pid,
        name="Test Product",
        price_inr=price,
        stock=stock,
        category="shoes",
        description="A test product",
        return_policy="30 days",
    )


def _make_cart(total: float = 5000, unit_price: float = 5000, qty: int = 1) -> Cart:
    return Cart(
        cart_id="c-test",
        merchant_id="m1",
        mandate_id="mandate-1",
        items=[CartItem(product_id="p1", quantity=qty, unit_price_inr=unit_price)],
        upsell_items=[],
        total_inr=total,
        idempotency_key="idem-test",
    )


def _mock_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_cart_passes():
    product = _make_product(price=5000, stock=10)
    cart = _make_cart(total=5000, unit_price=5000)
    rules = _make_rules()
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is True


def test_out_of_stock_blocked():
    product = _make_product(price=5000, stock=0)
    cart = _make_cart(total=5000, unit_price=5000, qty=1)
    rules = _make_rules()
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is False
    assert "stock" in result.reason.lower()


def test_partial_stock_blocked():
    product = _make_product(price=5000, stock=2)
    cart = _make_cart(total=15000, unit_price=5000, qty=3)
    rules = _make_rules()
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is False
    assert "stock" in result.reason.lower()


def test_over_discount_blocked():
    product = _make_product(price=5000, stock=10)
    # 10% max discount → floor = ₹4500; price ₹4000 is below floor
    cart = _make_cart(total=4000, unit_price=4000)
    rules = _make_rules(max_ai_discount_pct=10.0)
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is False
    assert "discount" in result.reason.lower() or "floor" in result.reason.lower()


def test_at_discount_floor_passes():
    product = _make_product(price=5000, stock=10)
    # Exactly at 10% discount floor: ₹4500
    cart = _make_cart(total=4500, unit_price=4500)
    rules = _make_rules(max_ai_discount_pct=10.0)
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is True


def test_over_approval_threshold_blocked():
    product = _make_product(price=12000, stock=10)
    cart = _make_cart(total=12000, unit_price=12000)
    rules = _make_rules(require_approval_above_inr=10000)
    db = _mock_db()
    result = policy_service.check(cart, rules, {"p1": product}, db)
    assert result.passed is False
    assert any(k in result.reason.lower() for k in ("threshold", "approval", "limit", "block"))


def test_unknown_product_blocked():
    cart = _make_cart(total=5000, unit_price=5000)
    rules = _make_rules()
    db = _mock_db()
    # products_by_id is empty — product not found
    result = policy_service.check(cart, rules, {}, db)
    assert result.passed is False
    assert "not found" in result.reason.lower()
