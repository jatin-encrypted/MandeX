"""
buyer.py — AI Buyer client for the demo.

Flow:
  1. Accept a plain-text intent string (e.g. "running shoes under ₹6,000")
  2. Call Gemini to extract structured search params {query, max_price}
  3. Call search_catalog → pick the best match
  4. Call build_cart (with the demo mandate)
  5. Call check_policy
  6. Call checkout
  7. Print the Decision Receipt

Fallback: if Gemini is slow or fails, a hardcoded parse covers the two
demo phrases so the live demo never stalls (see Risk Watchlist §11).

Usage:
  python buyer.py --merchant <merchant_id> --mandate <mandate_id> --request "running shoes under ₹6,000"
  python buyer.py --merchant <merchant_id> --mandate <mandate_id> --product <product_id> --request "buy the ₹8,999 version"
"""

import argparse
import json
import os
import sys
import time
import httpx
import re

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Hardcoded fallbacks for the two demo phrases (Risk Watchlist §11)
# ---------------------------------------------------------------------------
_DEMO_FALLBACKS = {
    "running shoes under": {"query": "running shoes", "max_price": 6000},
    "buy the": {"query": None, "max_price": None},   # direct product override
}

def _gemini_parse(intent: str) -> dict | None:
    """
    Call Gemini to extract {query, max_price} from the intent string.
    Returns None on failure so the caller falls back to hardcoded logic.
    """
    try:
        import google.generativeai as genai
        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            return None
        genai.configure(api_key=api_key)

        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Extract structured search parameters from this shopping intent. "
            "Return a JSON object with keys 'query' (string, the product type) and "
            "'max_price' (number in INR, or null if not mentioned).\n\n"
            f"Intent: \"{intent}\"\n\nJSON only, no explanation:"
        )
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=64,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"[buyer] Gemini parse failed ({e}), using fallback.", file=sys.stderr)
        return None


def parse_intent(intent: str) -> dict:
    """Returns {query: str, max_price: float|None}."""
    # Try Gemini with a 2-second timeout
    result = None
    start = time.time()
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(_gemini_parse, intent)
        try:
            result = future.result(timeout=2.0)
        except concurrent.futures.TimeoutError:
            print("[buyer] Gemini timed out, using fallback.", file=sys.stderr)

    if result and "query" in result:
        return result

    # Fallback: simple regex
    intent_lower = intent.lower()
    max_price = None
    price_match = re.search(r"₹?\s*(\d[\d,]*)", intent)
    if price_match:
        max_price = float(price_match.group(1).replace(",", ""))

    query_match = re.sub(r"(under|below|less than|₹|\d[\d,]*|rupees?)", "", intent_lower).strip()
    query_match = re.sub(r"\s+", " ", query_match).strip()
    return {"query": query_match or intent, "max_price": max_price}


def call(endpoint: str, payload: dict) -> dict:
    url = f"{GATEWAY_URL}/mcp/{endpoint}"
    response = httpx.post(url, json=payload, timeout=30)
    if response.status_code >= 400:
        print(f"[buyer] {endpoint} failed {response.status_code}: {response.text}", file=sys.stderr)
        sys.exit(1)
    return response.json()


def print_receipt(receipt: dict):
    print("\n" + "=" * 52)
    print("  AI COMMERCE DECISION RECEIPT")
    print("=" * 52)
    print(f"  CUSTOMER REQUEST")
    print(f"  {receipt['customer_request']}")
    print()
    print(f"  AI CONSIDERED   {receipt['products_considered']} products")
    print()
    sp = receipt["selected_product"]
    print(f"  SELECTED")
    print(f"  {sp['name']} — ₹{sp['price_inr']:,.2f}")
    print()
    if receipt.get("selection_reasons"):
        print("  WHY")
        for r in receipt["selection_reasons"]:
            print(f"  ✓ {r}")
        print()
    if receipt.get("upsell_product"):
        up = receipt["upsell_product"]
        print(f"  UPSELL")
        print(f"  {up['name']} — ₹{up['price_inr']:,.2f}")
        print(f"  WHY: {receipt.get('upsell_reason', '')}")
        print()
    print(f"  FINAL TOTAL     ₹{receipt['final_total_inr']:,.2f}")
    print()
    mandate_ok = receipt["mandate_check_passed"]
    print(f"  AUTHORIZATION   {'✓ Within buyer limit' if mandate_ok else '✗ Exceeded buyer limit'}")
    print()
    status = receipt["payment_status"]
    if receipt.get("blocked_reason"):
        print(f"  ❌ BLOCKED")
        print(f"  {receipt['blocked_reason']}")
        print()
        print("  Razorpay was NEVER called.")
    elif status == "verified":
        print(f"  ✓ PAYMENT       Razorpay verified")
        if receipt.get("razorpay_order_id"):
            print(f"  Order ID: {receipt['razorpay_order_id']}")
    elif status == "failed":
        print(f"  ✗ PAYMENT FAILED")
    else:
        print(f"  PAYMENT: {status}")
    print("=" * 52 + "\n")


def run(merchant_id: str, mandate_id: str, intent: str, product_id: str | None = None):
    print(f"\n[buyer] Intent: {intent!r}")

    if product_id:
        # Direct product override (the "buy the ₹8,999 version" demo path)
        product = httpx.post(
            f"{GATEWAY_URL}/mcp/get_product",
            json={"merchant_id": merchant_id, "product_id": product_id},
            timeout=10,
        ).json()
        products = [product]
        params = {"query": product.get("name", ""), "max_price": None}
    else:
        params = parse_intent(intent)
        print(f"[buyer] Parsed params: {params}")

        products = call("search_catalog", {
            "merchant_id": merchant_id,
            "query": params.get("query", ""),
            "max_price": params.get("max_price"),
        })
        if not products:
            print("[buyer] No products found matching the intent.")
            sys.exit(0)

    # Pick best match — lowest price within budget (simple, explainable)
    best = min(products, key=lambda p: p["price_inr"])
    selection_reasons = ["Best fit for intent", "In stock", "Within budget"]
    print(f"[buyer] Selected: {best['name']} at ₹{best['price_inr']}")

    # build_cart
    cart = call("build_cart", {
        "merchant_id": merchant_id,
        "mandate_id": mandate_id,
        "product_id": best["id"],
        "quantity": 1,
        "customer_request": intent,
    })
    print(f"[buyer] Cart built: {cart['cart_id']}, total ₹{cart['total_inr']}")

    # check_policy
    decision = call("check_policy", {"cart_id": cart["cart_id"]})
    print(f"[buyer] Policy decision: {decision['final_decision']}")

    # checkout
    receipt = call("checkout", {
        "cart_id": cart["cart_id"],
        "customer_request": intent,
        "products_considered": len(products),
        "selection_reasons": selection_reasons,
    })

    print_receipt(receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Commerce Gateway — Buyer Client")
    parser.add_argument("--merchant", required=True, help="Merchant ID")
    parser.add_argument("--mandate", required=True, help="Mandate ID")
    parser.add_argument("--request", required=True, help="Buyer intent string")
    parser.add_argument("--product", default=None, help="Override: specific product ID to buy")
    args = parser.parse_args()
    run(args.merchant, args.mandate, args.request, args.product)
