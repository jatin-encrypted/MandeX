import { useState, useCallback } from "react";
import {
  searchCatalog,
  buildCart,
  checkPolicy,
  checkout,
  getRazorpayPublicKey,
  verifyRazorpayPayment,
  type PolicyDecision,
  type Product,
  type DecisionReceipt,
} from "../lib/api";
import DecisionReceiptView from "./DecisionReceiptView";

const DEMO_MERCHANT_ID = import.meta.env.VITE_DEMO_MERCHANT_ID ?? "";
const DEMO_MANDATE_ID = import.meta.env.VITE_DEMO_MANDATE_ID ?? "";

// ---------------------------------------------------------------------------
// Razorpay checkout.js loader — injects the script once, resolves when ready
// ---------------------------------------------------------------------------
function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) { resolve(); return; }
    const existing = document.getElementById("razorpay-checkout-js");
    if (existing) { existing.addEventListener("load", () => resolve()); return; }
    const script = document.createElement("script");
    script.id = "razorpay-checkout-js";
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay checkout.js"));
    document.body.appendChild(script);
  });
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Step =
  | { status: "idle" }
  | { status: "running"; message: string }
  | { status: "awaiting_payment"; receipt: DecisionReceipt }
  | { status: "done"; receipt: DecisionReceipt }
  | { status: "error"; message: string };

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function DemoBuyerConsole() {
  const [merchantId, setMerchantId] = useState(DEMO_MERCHANT_ID);
  const [mandateId, setMandateId] = useState(DEMO_MANDATE_ID);
  const [request, setRequest] = useState("Find me running shoes under ₹6,000");
  const [step, setStep] = useState<Step>({ status: "idle" });
  const [log, setLog] = useState<string[]>([]);
  // Stores the full PolicyDecision from check_policy so both mandate and
  // policy sub-results can be shown in the UI from actual backend data.
  const [policyDecision, setPolicyDecision] = useState<PolicyDecision | null>(null);

  const addLog = (msg: string) =>
    setLog((l) => [...l, `${new Date().toLocaleTimeString()}  ${msg}`]);

  // -------------------------------------------------------------------------
  // launchRazorpayWidget — called only when the AI authorized the purchase
  // (order_verified state).  Opens the Razorpay Test Checkout widget.
  // On success, POSTs the payment details to our backend for server-side
  // HMAC verification before upgrading to payment_verified.
  // -------------------------------------------------------------------------
  const launchRazorpayWidget = useCallback(async (receipt: DecisionReceipt) => {
    if (!receipt.razorpay_order_id) return;

    addLog("Loading Razorpay checkout widget…");
    try {
      await loadRazorpayScript();
    } catch {
      addLog("ERROR: Could not load Razorpay checkout.js — check network.");
      return;
    }

    let keyId: string;
    try {
      const { key_id } = await getRazorpayPublicKey();
      keyId = key_id;
      addLog(`Razorpay key loaded: ${key_id}`);
    } catch {
      addLog("ERROR: Could not fetch Razorpay public key from backend.");
      return;
    }

    const amountPaise = Math.round(receipt.final_total_inr * 100);

    addLog(`Opening Razorpay Test Checkout for ₹${receipt.final_total_inr.toLocaleString("en-IN")}…`);

    const rzp = new window.Razorpay({
      key: keyId,
      amount: amountPaise,
      currency: "INR",
      name: "MandeX — AI Commerce Gateway",
      description: `AI purchase: ${receipt.selected_product?.name ?? ""}`,
      order_id: receipt.razorpay_order_id,
      prefill: { name: "Demo Buyer", email: "demo@mandex.ai" },
      theme: { color: "#C9A46A" },

      handler: async (response) => {
        addLog(`Payment captured by Razorpay: ${response.razorpay_payment_id}`);
        addLog("Sending payment details to backend for signature verification…");
        try {
          const verified = await verifyRazorpayPayment({
            cart_id: receipt.cart_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_order_id: response.razorpay_order_id,
            razorpay_signature: response.razorpay_signature,
          });
          addLog(`Backend verification: ${verified.payment_status}`);
          // Upgrade the receipt display to payment_verified
          setStep({
            status: "done",
            receipt: {
              ...receipt,
              payment_status: "payment_verified",
              razorpay_payment_id: verified.razorpay_payment_id,
            },
          });
        } catch {
          addLog("ERROR: Backend signature verification failed — payment not confirmed.");
          setStep({ status: "error", message: "Backend failed to verify Razorpay signature." });
        }
      },

      modal: {
        ondismiss: () => {
          addLog("Razorpay widget dismissed by user — payment not completed.");
          // Leave receipt in order_verified state — the AI did its job; human closed widget
          setStep({ status: "done", receipt });
        },
      },
    });

    rzp.open();
  }, []);

  // -------------------------------------------------------------------------
  // run — the AI buyer flow: search → build_cart → check_policy → checkout
  // -------------------------------------------------------------------------
  const run = async () => {
    setLog([]);
    setStep({ status: "running", message: "AI searching catalog…" });
    setPolicyDecision(null);

    try {
      // -----------------------------------------------------------------------
      // Intent parsing — two distinct paths:
      //
      // PATH A — Exact-price request: "Buy the ₹8,999 version" / "₹X,XXX version"
      //   The buyer is naming a specific product by price.  We must pick the
      //   product whose catalog price EQUALS that amount, NOT the cheapest one
      //   under that ceiling.  This is what gates the mandate-BLOCK demo path.
      //
      // PATH B — Budget search: "Find me running shoes under ₹6,000"
      //   Normal catalog search with max_price filter; pick lowest-price match.
      // -----------------------------------------------------------------------
      const exactVersionPattern = /(?:buy\s+the\s+)?₹\s*([\d,]+)\s+version/i;
      const exactVersionMatch = request.match(exactVersionPattern);

      let products: Product[];
      let best: Product;

      if (exactVersionMatch) {
        // PATH A — find the product at exactly this price
        const targetPrice = parseFloat(exactVersionMatch[1].replace(/,/g, ""));
        addLog(`[AI] Exact-price request detected: ₹${targetPrice.toLocaleString("en-IN")}`);
        addLog(`[AI] search_catalog(query="", max_price=none) — scanning full catalog for match`);

        products = await searchCatalog(merchantId, "", undefined);
        addLog(`  → ${products.length} product${products.length !== 1 ? "s" : ""} in catalog`);

        if (products.length === 0) {
          setStep({ status: "error", message: "No products found in catalog." });
          return;
        }

        // Match product at the stated price within ₹1 tolerance (float safety)
        const exactMatch = products.find(
          (p) => Math.abs(p.price_inr - targetPrice) < 1.0
        );
        // Fallback: most expensive if no exact match (still demonstrates blocking)
        best = exactMatch ?? products.reduce((a, b) =>
          a.price_inr >= b.price_inr ? a : b
        );
        addLog(
          exactMatch
            ? `[AI] Exact-price match found: ${best.name} at ₹${best.price_inr.toLocaleString("en-IN")}`
            : `[AI] No exact match for ₹${targetPrice.toLocaleString("en-IN")} — using most expensive: ${best.name}`
        );
      } else {
        // PATH B — budget search ("Find me running shoes under ₹6,000")
        const priceMatch = request.match(/₹?\s*(\d[\d,]*)/);
        const maxPrice = priceMatch
          ? parseFloat(priceMatch[1].replace(/,/g, ""))
          : undefined;
        const query = request
          .replace(/under.*|below.*|less than.*/i, "")
          .replace(/find me|buy|the|version/gi, "")
          .trim();

        addLog(`[AI] search_catalog(query="${query}", max_price=${maxPrice ?? "any"})`);
        products = await searchCatalog(merchantId, query, maxPrice);
        addLog(`  → ${products.length} result${products.length !== 1 ? "s" : ""}`);

        if (products.length === 0) {
          setStep({ status: "error", message: "No products found matching this request." });
          return;
        }

        // AI picks best match — lowest price within budget (deterministic, not ML)
        best = products.reduce((a, b) =>
          a.price_inr <= b.price_inr ? a : b
        );
        addLog(`[AI] Selected: ${best.name} at ₹${best.price_inr.toLocaleString("en-IN")}`);
      }

      setStep({ status: "running", message: "AI building cart…" });
      addLog(`[AI] build_cart(product_id=${best.id}, mandate_id=${mandateId.slice(0, 8)}…)`);
      const cart = await buildCart({
        merchant_id: merchantId,
        mandate_id: mandateId,
        product_id: best.id,
        quantity: 1,
        customer_request: request,
      });
      addLog(`  → cart ${cart.cart_id.slice(0, 8)}, total ₹${cart.total_inr.toLocaleString("en-IN")}`);

      setStep({ status: "running", message: "Checking buyer mandate + merchant policy…" });
      addLog(`[AI] check_policy(cart_id=${cart.cart_id.slice(0, 8)}…)`);
      const decision = await checkPolicy(cart.cart_id);
      // Store the full PolicyDecision so the UI can show actual mandate/policy results
      setPolicyDecision(decision);
      addLog(
        `  → ${decision.final_decision} | mandate: ${decision.mandate_check_passed ? "PASS" : "FAIL"} | policy: ${decision.policy_check_passed ? "PASS" : "FAIL"}`
      );

      setStep({ status: "running", message: "AI initiating checkout…" });
      addLog(`[AI] checkout(cart_id=${cart.cart_id.slice(0, 8)}…)`);
      const receipt = await checkout({
        cart_id: cart.cart_id,
        customer_request: request,
        products_considered: products.length,
        selection_reasons: ["Best match for intent", "In stock", "Within mandate budget"],
      });
      addLog(`  → payment_status: ${receipt.payment_status}`);

      if (receipt.blocked_reason) {
        addLog(`  → BLOCKED: ${receipt.blocked_reason}`);
        setStep({ status: "done", receipt });
        return;
      }

      if (receipt.payment_status === "order_verified" && receipt.razorpay_order_id) {
        addLog(`  → Razorpay order created: ${receipt.razorpay_order_id}`);
        addLog("[AI] Purchase authorized. Opening Razorpay Test Checkout for payment…");
        setStep({ status: "awaiting_payment", receipt });
        // Launch the widget — async, will upgrade to payment_verified on success
        launchRazorpayWidget(receipt);
        return;
      }

      // Already payment_verified (e.g. idempotent retry that was already paid)
      setStep({ status: "done", receipt });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      addLog(`ERROR: ${msg}`);
      setStep({ status: "error", message: msg });
    }
  };

  const currentReceipt =
    step.status === "done" || step.status === "awaiting_payment"
      ? step.receipt
      : null;

  return (
    <div className="min-h-screen bg-ink px-4 py-12">
      <div className="max-w-2xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-text-ink text-xl font-semibold">Demo Buyer Console</h1>
          <p className="text-text-ink/50 text-sm mt-1">
            An AI purchasing agent operating within a buyer mandate and merchant policy.
          </p>
        </div>

        {/* Config fields */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <label className="block text-xs text-text-ink/60">
            Merchant ID
            <input
              value={merchantId}
              onChange={(e) => setMerchantId(e.target.value)}
              className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-xs mono focus:outline-none focus:border-gold"
              placeholder="demo-merchant-001"
            />
          </label>
          <label className="block text-xs text-text-ink/60">
            Mandate ID
            <input
              value={mandateId}
              onChange={(e) => setMandateId(e.target.value)}
              className="mt-1 block w-full bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-xs mono focus:outline-none focus:border-gold"
              placeholder="Mandate ID from seed output"
            />
          </label>
        </div>

        {/* Request input */}
        <div className="mb-4">
          <label className="block text-xs text-text-ink/60 mb-1">Buyer request</label>
          <div className="flex gap-2">
            <input
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()}
              className="flex-1 bg-ink-raised border border-ink-raised/80 text-text-ink px-3 py-2 text-sm focus:outline-none focus:border-gold"
              placeholder='"Find me running shoes under ₹6,000"'
            />
            <button
              onClick={run}
              disabled={step.status === "running" || step.status === "awaiting_payment" || !merchantId || !mandateId}
              className="px-4 py-2 bg-gold text-text-paper text-sm font-medium disabled:opacity-40"
            >
              {step.status === "running" ? "Running…" : "Run"}
            </button>
          </div>
        </div>

        {/* Quick demo shortcuts */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setRequest("Find me running shoes under ₹6,000")}
            className="text-xs text-text-ink/50 border border-ink-raised px-2 py-1 hover:border-gold hover:text-gold transition-colors"
          >
            Happy path
          </button>
          <button
            onClick={() => setRequest("Buy the ₹8,999 version instead")}
            className="text-xs text-text-ink/50 border border-ink-raised px-2 py-1 hover:border-blocked hover:text-blocked transition-colors"
          >
            Blocked path
          </button>
        </div>

        {/* Step log */}
        {log.length > 0 && (
          <div className="bg-ink-raised border border-ink-raised/80 p-4 mb-6 font-mono text-xs text-text-ink/60 space-y-1 max-h-48 overflow-y-auto">
            {log.map((line, i) => (
              <p key={i}>{line}</p>
            ))}
          </div>
        )}

        {/* Error banner */}
        {step.status === "error" && (
          <div className="bg-blocked/10 border border-blocked/30 p-4 mb-6">
            <p className="text-blocked text-sm">{step.message}</p>
          </div>
        )}

        {/* AI Purchase Authorization Panel
             Shown for BOTH approved and blocked outcomes — uses live PolicyDecision
             data from the backend, never hardcoded values. */}
        {policyDecision && currentReceipt && (
          <div
            className={`bg-ink-raised border p-4 mb-4 ${
              currentReceipt.blocked_reason ? "border-blocked/30" : "border-gold/30"
            }`}
          >
            <p
              className={`text-xs font-medium mb-3 uppercase tracking-wide ${
                currentReceipt.blocked_reason ? "text-blocked" : "text-gold"
              }`}
            >
              {currentReceipt.blocked_reason ? "Purchase Blocked" : "AI Purchase Authorization"}
            </p>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-text-ink/50">Final decision</span>
                <span
                  className={`font-medium ${
                    currentReceipt.blocked_reason ? "text-blocked" : "text-verified"
                  }`}
                >
                  {currentReceipt.blocked_reason
                    ? "✗ BLOCKED"
                    : currentReceipt.payment_status === "payment_verified"
                    ? "✓ Payment verified"
                    : currentReceipt.payment_status === "order_verified" ||
                      step.status === "awaiting_payment"
                    ? "◎ Awaiting payment"
                    : "✓ Approved"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-ink/50">Buyer mandate</span>
                <span
                  className={policyDecision.mandate_check_passed ? "text-verified" : "text-blocked"}
                >
                  {policyDecision.mandate_check_passed ? "PASS" : "FAIL"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-ink/50">Merchant policy</span>
                <span
                  className={policyDecision.policy_check_passed ? "text-verified" : "text-blocked"}
                >
                  {policyDecision.policy_check_passed ? "PASS" : "FAIL"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-ink/50">Cart total</span>
                <span className="mono text-text-ink">
                  ₹{currentReceipt.final_total_inr.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </span>
              </div>
              {currentReceipt.razorpay_order_id && (
                <div className="flex justify-between">
                  <span className="text-text-ink/50">Razorpay order</span>
                  <span className="mono text-text-ink/70 text-xs">
                    {currentReceipt.razorpay_order_id}
                  </span>
                </div>
              )}
              {currentReceipt.razorpay_payment_id && (
                <div className="flex justify-between">
                  <span className="text-text-ink/50">Payment ID</span>
                  <span className="mono text-verified text-xs">
                    {currentReceipt.razorpay_payment_id}
                  </span>
                </div>
              )}
              {currentReceipt.payment_status === "payment_verified" && (
                <div className="flex justify-between mt-2 pt-2 border-t border-gold/20">
                  <span className="text-text-ink/50">Verification</span>
                  <span className="text-verified font-medium">✓ Server-verified signature</span>
                </div>
              )}
              {currentReceipt.blocked_reason && (
                <div className="mt-2 pt-2 border-t border-blocked/20">
                  <p className="text-blocked/70 text-xs italic">Razorpay was never called.</p>
                </div>
              )}
            </div>

            {step.status === "awaiting_payment" && (
              <div className="mt-3 pt-3 border-t border-gold/20">
                <button
                  onClick={() => launchRazorpayWidget(currentReceipt)}
                  className="w-full py-2 bg-gold text-text-paper text-sm font-medium"
                >
                  Open Razorpay Test Checkout
                </button>
                <p className="text-text-ink/30 text-xs mt-1.5 text-center">
                  Use test card: 4111 1111 1111 1111 · Exp any · CVV any
                </p>
              </div>
            )}
          </div>
        )}

        {/* Decision Receipt */}
        {currentReceipt && (
          <DecisionReceiptView receipt={currentReceipt} />
        )}
      </div>
    </div>
  );
}
