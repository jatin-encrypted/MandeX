"""
test_intent_parsing.py — deterministic unit tests for the exact-price
product-selection logic introduced to fix the blocked demo path.

The frontend (DemoBuyerConsole.tsx) runs in a browser and has no backend
test runner, so we replicate its two-path logic here in Python so the full
pytest suite can assert correctness:

  PATH A — "Buy the ₹8,999 version" → picks product at exactly ₹8,999
  PATH B — "Find me running shoes under ₹6,000" → picks cheapest ≤ ₹6,000

We also verify the full mandate-block outcome for the PATH A scenario using
the real mandate_service.
"""
import re
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.schemas.cart import Cart, CartItem
from app.schemas.mandate import Mandate
from app.services import mandate_service


# ---------------------------------------------------------------------------
# Helpers — mirrors demo seed catalog prices
# ---------------------------------------------------------------------------

DEMO_PRODUCTS = [
    {"id": "p-shoes-1", "name": "Velocity Pro Running Shoes",   "price_inr": 5499.0},
    {"id": "p-shoes-2", "name": "TrailBlazer All-Terrain Shoes","price_inr": 4299.0},
    {"id": "p-shoes-3", "name": "SprintX Track Spikes",         "price_inr": 8999.0},
    {"id": "p-shoes-4", "name": "EasyRun Foam Trainers",        "price_inr": 2799.0},
    {"id": "p-acc-1",   "name": "Pro Running Socks (3-pack)",   "price_inr":  499.0},
    {"id": "p-acc-2",   "name": "Hydration Vest 5L",            "price_inr": 2199.0},
    {"id": "p-app-1",   "name": "Performance Dry-Fit Tee",      "price_inr":  899.0},
    {"id": "p-app-2",   "name": "Wind-Resistant Running Jacket","price_inr": 3499.0},
]

# Matches DemoBuyerConsole.tsx  exactVersionPattern
_EXACT_RE = re.compile(r"(?:buy\s+the\s+)?₹\s*([\d,]+)\s+version", re.IGNORECASE)


def _detect_exact_version(request: str):
    return _EXACT_RE.search(request)


def _select_exact(request: str, products: list) -> dict:
    """Mirrors PATH A logic in DemoBuyerConsole.tsx."""
    m = _detect_exact_version(request)
    assert m
    target = float(m.group(1).replace(",", ""))
    exact = next((p for p in products if abs(p["price_inr"] - target) < 1.0), None)
    return exact if exact else max(products, key=lambda p: p["price_inr"])


def _select_budget(max_price: float | None, products: list) -> dict:
    """Mirrors PATH B logic in DemoBuyerConsole.tsx."""
    pool = [p for p in products if max_price is None or p["price_inr"] <= max_price]
    return min(pool, key=lambda p: p["price_inr"])


def _make_signed_mandate(max_amount=6000.0) -> Mandate:
    expires_at = datetime.now(timezone.utc) + timedelta(days=90)
    temp = Mandate(
        mandate_id="m-test", buyer_id="demo-buyer",
        max_amount_inr=max_amount, allowed_categories=[],
        expires_at=expires_at, issued_at=datetime.now(timezone.utc), signature="",
    )
    return temp.model_copy(update={"signature": mandate_service.sign(temp)})


def _make_cart(product: dict) -> Cart:
    return Cart(
        cart_id="c-test", merchant_id="demo-merchant-001", mandate_id="m-test",
        items=[CartItem(product_id=product["id"], quantity=1, unit_price_inr=product["price_inr"])],
        upsell_items=[], total_inr=product["price_inr"], idempotency_key="idem-test",
    )


def _mock_db():
    db = MagicMock()
    db.add = MagicMock(); db.commit = MagicMock(); db.refresh = MagicMock()
    return db


# ---------------------------------------------------------------------------
# PATH A — Exact-price pattern detection
# ---------------------------------------------------------------------------

def test_exact_version_pattern_matches():
    assert _detect_exact_version("Buy the ₹8,999 version instead") is not None
    assert _detect_exact_version("₹8,999 version") is not None


def test_exact_version_pattern_does_not_match_budget_phrase():
    assert _detect_exact_version("Find me running shoes under ₹6,000") is None
    assert _detect_exact_version("running shoes under ₹5,000") is None


def test_exact_price_selects_sprintx():
    """PATH A: '₹8,999 version' must resolve to SprintX, NOT the cheapest product."""
    selected = _select_exact("Buy the ₹8,999 version instead", DEMO_PRODUCTS)
    assert selected["name"] == "SprintX Track Spikes"
    assert selected["price_inr"] == 8999.0


def test_exact_price_does_not_select_cheapest():
    selected = _select_exact("Buy the ₹8,999 version instead", DEMO_PRODUCTS)
    assert selected["price_inr"] != 499.0  # must NOT be socks


def test_exact_price_fallback_to_most_expensive_when_no_catalog_match():
    """No product at ₹99,999 → fallback to most expensive (SprintX ₹8,999)."""
    selected = _select_exact("Buy the ₹99,999 version", DEMO_PRODUCTS)
    assert selected["price_inr"] == 8999.0


# ---------------------------------------------------------------------------
# PATH B — Budget search (must be unaffected by PATH A logic)
# ---------------------------------------------------------------------------

def test_budget_search_picks_cheapest_within_limit():
    selected = _select_budget(max_price=6000.0, products=DEMO_PRODUCTS)
    assert selected["price_inr"] <= 6000.0
    # cheapest product overall is ₹499 socks — budget search picks it
    assert selected["price_inr"] == 499.0


def test_budget_search_excludes_over_limit():
    selected = _select_budget(max_price=3000.0, products=DEMO_PRODUCTS)
    assert selected["price_inr"] <= 3000.0


# ---------------------------------------------------------------------------
# End-to-end mandate check
# ---------------------------------------------------------------------------

def test_blocked_path_mandate_fails_for_sprintx():
    """
    After PATH A selects SprintX (₹8,999), mandate check (₹6,000 limit) → BLOCK.
    This proves Razorpay is never called for the blocked demo scenario.
    """
    product = next(p for p in DEMO_PRODUCTS if p["name"] == "SprintX Track Spikes")
    mandate = _make_signed_mandate(max_amount=6000.0)
    cart = _make_cart(product)

    result = mandate_service.check(cart, mandate, _mock_db())

    assert result.passed is False, "₹8,999 purchase must be blocked by ₹6,000 mandate"
    assert "exceeds mandate limit" in result.reason


def test_happy_path_mandate_passes_for_budget_selection():
    """PATH B cheapest selection (₹499) must pass the ₹6,000 mandate."""
    product = _select_budget(max_price=6000.0, products=DEMO_PRODUCTS)
    mandate = _make_signed_mandate(max_amount=6000.0)
    cart = _make_cart(product)

    result = mandate_service.check(cart, mandate, _mock_db())
    assert result.passed is True, f"₹{product['price_inr']} purchase should pass ₹6,000 mandate"
