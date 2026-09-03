# AI Commerce Gateway — Product Requirements Document

**Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

---

## 1. Problem Statement

Most merchants have an online store built for **humans**. A person can read a product page, understand the price, check stock, and buy. An **AI shopping agent** cannot reliably do this — commerce information is scattered across pages, inconsistently formatted, and meant for visual browsing, not machine reasoning.

As AI assistants increasingly shop on a user's behalf ("find me running shoes under ₹6,000 and buy them"), a merchant can be doing great business with human customers and still be **invisible or untransactable** to an AI buyer.

## 2. Product Statement

> **AI Commerce Gateway** is a merchant-side infrastructure layer that converts a merchant's commerce data into an AI-readable **Commerce Passport**, exposes it to AI agents through **MCP**, and lets those agents discover, decide, and purchase products through **Razorpay** — within explicit buyer and merchant policies. Every decision is explainable, every financial action is gated, and every transaction is audited.

**One sentence:** *We are the layer that makes a merchant ready for AI buyers.*

## 3. What We Are / Are Not Building

| We ARE building | We are NOT building |
|---|---|
| The infrastructure layer that makes a merchant AI-buyer-ready and transactable end to end | An AI shopping chatbot |
| A structured, platform-independent commerce data format (Commerce Passport) | A Google-like product search engine |
| A bounded, gated, auditable checkout path for AI agents | A universal web scraper |
| | An AI with direct, unbounded access to money |

---

## 4. Core Flow

```
Merchant
   │
Connects store / uploads catalog / fills dashboard
   │
   ▼
Gateway structures the data → Commerce Passport
   │
Merchant reviews & confirms → Commerce Passport ACTIVE
   │
   ▼
Merchant configures optional rules
  (max AI discount, upsells on/off, preferred categories,
   minimum margin, require-approval-above threshold)
   │
   ▼
Gateway exposes merchant via MCP tools
  (search_catalog, get_product, build_cart, check_policy, checkout)
   │
   ▼
AI Buyer states intent
  ("Find me running shoes under ₹6,000")
   │
   ▼
Decision Engine considers:
  intent + budget + product fit + availability +
  merchant rules + (optional) merchant economics
   │
   ▼
Build Cart
   │
   ▼
Mandate Check (buyer-side)
  Does the agent's spending authority (amount / category / expiry)
  cover this cart?
   │
   ▼
Policy Gate (merchant-side)
  Deterministic checks: stock, margin floor, discount limits,
  approval thresholds
   │
   ├── APPROVE ──▶ Razorpay executes payment ──▶ Verification
   │                (quoted vs. charged/fulfilled match)
   │
   └── BLOCK ───▶ Explanation returned, Razorpay never called
   │
   ▼
Explain + Audit Log
  Customer sees: what was selected, why, price, authorization, final action
  Merchant sees: transactions, revenue, AI decisions, policy events
```

---

## 5. Onboarding — Two Modes

**Mode 1 — Merchant-Provided Data (MVP, hackathon scope)**
Merchant directly supplies and confirms their catalog, pricing, stock, and rules via a dashboard, file upload, or API connection. Because the merchant authorizes the data themselves, **no AI confidence scoring is needed** — the merchant is the ground truth. The Gateway still performs **structural validation** (e.g., price below cost given stated margin, missing required fields) before marking a Commerce Passport ACTIVE.

**Mode 2 — Automatic Website Extraction (future feature, not core to MVP)**
Gateway scrapes and infers structured data from an arbitrary live website. This is where extraction confidence genuinely matters (e.g., "₹4,999 onwards" is ambiguous) — deferred as a stretch goal, not required for the demo.

This framing also answers the "what about Shopify / WooCommerce / Magento / a custom site?" question cleanly: *"Our core layer is platform-independent. The merchant connects their store, API, or catalog data in whatever form they have it; the Gateway normalizes it into the same Commerce Passport."*

---

## 6. Core Components

### 6.1 Commerce Passport
Structured, platform-independent representation of a merchant's catalog and rules: products, prices, stock, policies (returns/delivery/payment), plus merchant-configured rules (max AI discount, upsell on/off, preferred categories, minimum margin, approval threshold).

### 6.2 MCP Tool Layer
Exposes the merchant to AI agents via standardized tools:
- `search_catalog`
- `get_product`
- `build_cart`
- `check_policy`
- `checkout`

### 6.3 Decision Engine (AI Buyer side)
Interprets buyer intent and selects products considering intent, budget, product fit, availability, and merchant rules. This is where the actual AI reasoning in the system lives — the merchant-facing side is deliberately deterministic.

### 6.4 Mandate Check
Validates that the AI agent's claimed spending authority (max amount, category, expiry) covers the proposed cart, **before** any merchant policy or payment step. Kept as a distinct internal check even though it may be presented alongside the Policy Gate in the demo.

### 6.5 Policy Gate
Deterministic merchant-side checks: stock availability, minimum margin, discount limits, approval thresholds. Produces APPROVE or BLOCK, always with a logged reason.

### 6.6 Razorpay Integration
Executes payment only after Mandate Check + Policy Gate approve. Test-mode order APIs, ACP-shaped checkout flow (create → confirm → complete).

### 6.7 Verification
Post-payment check that the quoted price/stock matches what was actually charged/fulfilled. This is the "one graceful failure" surface — a mismatch is caught and logged, never silently accepted.

### 6.8 Audit Log
Append-only log written at every stage: Commerce Passport activation, mandate checks, policy decisions, payments, verification results. Powers both the customer-facing Decision Receipt and the merchant-facing transaction dashboard.

---

## 7. Signature Demo Feature: AI Commerce Decision Receipt

Every purchase produces a receipt that makes the AI's reasoning and the system's guardrails visible:

```
CUSTOMER REQUEST
Running shoes under ₹6,000

AI CONSIDERED
18 products

SELECTED
Velocity Pro — ₹5,499

WHY
✓ Best fit for intent
✓ In stock
✓ Within budget

UPSELL
Socks — ₹499
WHY: Highest-value eligible complement

FINAL
₹5,998

AUTHORIZATION
✓ Within buyer limit

PAYMENT
✓ Razorpay verified
```

**Paired live demo — the BLOCKED case:**

```
Request: "Buy the ₹8,999 version instead."

❌ BLOCKED
Buyer limit: ₹6,000
Requested:   ₹8,999

Razorpay was never called.
```

This pair is the single strongest proof point for "bounded, gated, explainable agentic commerce" — showing Razorpay was never invoked is more convincing than any architecture slide.

---

## 8. Build Order (dependency-sequenced, not diagram-sequenced)

1. **Merchant Dashboard + Commerce Passport** (Mode 1 onboarding, structural validation, no confidence scoring)
2. **MCP tool layer** — expose search/get/build_cart/checkout; build a simple scripted AI Buyer client to call it
3. **Mandate Check** — buyer authority validation (highest value-to-effort ratio)
4. **Merchant rules + Policy Gate** — rules engine (explainable if/else, not ML), combining mandate result + stock + margin
5. **Razorpay checkout + Verification** — wire approved carts to test-mode payment, check quoted vs. charged
6. **Audit Log** — written incrementally at every stage above, not bolted on at the end
7. **Demo polish** — script the happy path + the BLOCKED case; rehearse the 3-minute walkthrough

---

## 9. Explicit Scope Cuts (stretch goals, not MVP)

| Cut for MVP | Why | Where it would go if time allows |
|---|---|---|
| ML-driven dynamic pricing | Needs training data not available; hurts explainability | After Mode 1 rules-based pricing is solid |
| Fully autonomous AI Buyer | Reliability/debugging surface too large for the timeframe | Swap scripted client for an LLM-driven one using existing MCP tools |
| Automatic website extraction (Mode 2) | Open-ended scraping robustness problem; single biggest on-stage failure risk | Bounded version first (e.g., common e-commerce templates), full generality later |

---

## 10. Why Now (market context)

NPCI's Unified Agent Protocol (UAP) and the global protocol race (ACP, AP2, x402) make agent-to-agent commerce the open infrastructure problem of the moment, and Razorpay's own in-app agentic pilots are already live. A merchant being "AI-buyer-ready" is becoming a real, measurable gap — this project is the layer that closes it.
