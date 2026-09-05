"""
test_mandate_service.py — priority tests for mandate_service.check().
Per build plan §10: mandate and policy are exactly what "bounded and gated"
means in the track's grading bar — a bug here is a judged failure.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from app.schemas.mandate import Mandate, MandateCreateRequest
from app.schemas.cart import Cart, CartItem
from app.services import mandate_service


def _make_mandate(
    max_amount: float = 6000,
    categories: list[str] | None = None,
    expires_delta: timedelta = timedelta(days=30),
    buyer_id: str = "test-buyer",
) -> Mandate:
    """Helper — creates a properly signed Mandate."""
    expires_at = datetime.now(timezone.utc) + expires_delta
    issued_at = datetime.now(timezone.utc)
    temp = Mandate(
        mandate_id="m-test",
        buyer_id=buyer_id,
        max_amount_inr=max_amount,
        allowed_categories=categories or [],
        expires_at=expires_at,
        issued_at=issued_at,
        signature="",
    )
    sig = mandate_service.sign(temp)
    return temp.model_copy(update={"signature": sig})


def _make_cart(total: float = 5000, merchant_id: str = "m1") -> Cart:
    return Cart(
        cart_id="c-test",
        merchant_id=merchant_id,
        mandate_id="m-test",
        items=[CartItem(product_id="p1", quantity=1, unit_price_inr=total)],
        upsell_items=[],
        total_inr=total,
        idempotency_key="idem-test",
    )


def _mock_db():
    """Return a mock Session that swallows audit log writes."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_valid_mandate_passes():
    mandate = _make_mandate(max_amount=6000)
    cart = _make_cart(total=5499)
    db = _mock_db()
    result = mandate_service.check(cart, mandate, db)
    assert result.passed is True


def test_over_limit_amount_blocked():
    mandate = _make_mandate(max_amount=6000)
    cart = _make_cart(total=8999)
    db = _mock_db()
    result = mandate_service.check(cart, mandate, db)
    assert result.passed is False
    assert "exceeds mandate limit" in result.reason


def test_exact_limit_passes():
    mandate = _make_mandate(max_amount=6000)
    cart = _make_cart(total=6000)
    db = _mock_db()
    result = mandate_service.check(cart, mandate, db)
    assert result.passed is True


def test_expired_mandate_blocked():
    mandate = _make_mandate(expires_delta=timedelta(seconds=-1))
    cart = _make_cart(total=100)
    db = _mock_db()
    result = mandate_service.check(cart, mandate, db)
    assert result.passed is False
    assert "expired" in result.reason.lower()


def test_tampered_signature_blocked():
    mandate = _make_mandate(max_amount=6000)
    # Tamper: raise the limit without re-signing
    tampered = mandate.model_copy(update={"max_amount_inr": 99999.0})
    cart = _make_cart(total=50000)
    db = _mock_db()
    result = mandate_service.check(cart, tampered, db)
    assert result.passed is False
    assert "signature" in result.reason.lower()


def test_signature_verify_roundtrip():
    mandate = _make_mandate(max_amount=6000)
    assert mandate_service.verify_signature(mandate) is True


def test_signature_broken_after_field_change():
    mandate = _make_mandate(max_amount=6000)
    tampered = mandate.model_copy(update={"buyer_id": "evil-buyer"})
    assert mandate_service.verify_signature(tampered) is False
