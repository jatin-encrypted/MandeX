# Untitled

# AI Commerce Gateway

**Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

---

## One-sentence pitch

AI Commerce Gateway is a merchant-side infrastructure layer that converts a merchant's commerce data into an AI-readable **Commerce Passport**, exposes it to AI agents through **MCP**, and lets those agents recommend and purchase products through **Razorpay** — within explicit buyer and merchant limits. Every decision is explainable, every financial action is gated, every transaction is audited.

---

## The problem

Most merchants sell successfully to humans but are invisible or unusable to AI shopping agents, because their product, price, and policy information isn't structured in a way a machine can act on. As AI assistants start shopping on a user's behalf ("find me running shoes under ₹6,000and buy them"), merchants need a way to become **discoverable, trustworthy, and transactable** by those agents — without rebuilding their store.

---

## Onboarding: two modes

**Mode 1 — Merchant-provided data (the hackathon MVP)**
The merchant directly supplies and confirms their catalog, pricing, stock, and rules through a simple dashboard (upload/connect catalog, or manual entry). Because the merchant is the authoritative source, there is **no AI confidence-scoring layer** on this data — only basic **schema/range validation** (e.g. flag a product priced below its stated minimum margin) before the Commerce Passport goes live.

**Mode 2 — Automatic website extraction (future feature, not core to the demo)**
Scraping an arbitrary live website is a genuinely hard, open-ended problem. This mode is explicitly out of MVP scope. If built later, this is where per-field confidence scoring belongs — not in Mode 1.

This framing also answers the "what about Shopify/WooCommerce/Magento/a custom site?" question cleanly: *"Our core layer is platform-independent — the merchant connects their store, API, or catalog data, and the Gateway normalizes it into the same Commerce Passport."*

---

## End-to-end flow

1. **Merchant onboards** — connects store/catalog or uploads data via the dashboard
2. **Gateway structures the data** into a normalized **Commerce Passport** (product, price, stock, policy schema)
3. **Merchant reviews & confirms** — schema/range validation runs, merchant approves
4. **Merchant configures rules** — e.g. maximum AI discount, AI upsell on/off, preferred categories, minimum margin, "require approval above ₹X"
5. **Commerce Passport goes ACTIVE**
6. **Gateway exposes the merchant via MCP tools**: `search_catalog`, `get_product`, `build_cart`, `check_policy`, `checkout`
7. **AI buyer states intent** — e.g. *"Find me running shoes under ₹6,000"*
8. **Decision engine reasons** over intent + budget + product fit + availability + merchant rules (this is where the actual AI/LLM reasoning lives)
9. **Mandate Check** — does the agent's spending authority (amount, category, expiry) cover this cart? *(kept as a distinct internal check from merchant policy, even if presented as one gate)*
10. **Merchant Policy Gate** — margin floor, stock, discount/upsell rules
11. **Approve → Razorpay executes** the transaction (test-mode); **Block → explanation returned**, Razorpay is never called
12. **Verification** — does the quoted price/stock match what was actually charged/fulfilled?
13. **Explain + Audit Log** — every step (extraction/validation, mandate check, policy decision, payment, verification) is logged

---

## Architecture

```
                 MERCHANT
                    │
         Catalog / Store Connection
                    │
                    ▼
        ┌─────────────────────┐
        │ AI COMMERCE GATEWAY │
        │                     │
        │ Data Structuring    │
        │ Validation          │
        │ Commerce Passport   │
        └─────────┬───────────┘
                  │  MCP (tool discovery)
                  ▼
             AI BUYER
                  │
        "Buy running shoes
            under ₹6k"
                  │
                  ▼
          Decision Engine
       (intent, budget, fit,
      availability, merchant rules)
                  │
                  ▼
           Mandate Check          ← buyer's spending authority
                  │
                  ▼
           Policy Gate            ← merchant's rules
           /         \
       APPROVE       BLOCK
          │             │
          ▼             ▼
      Razorpay      Explanation
          │
          ▼
       Verification
          │
          ▼
    Audit Log ← every step above writes here
```

---

## The hero feature: AI Commerce Decision Receipt

Instead of the agent just saying "I picked this," it shows its work:

**Approved case:**

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

**Blocked case (the proof of "bounded, gated, explainable"):**

```
Request: "Buy the ₹8,999 version"

❌ BLOCKED
Buyer limit: ₹6,000
Requested: ₹8,999
Razorpay was never called.
```

This receipt is what a judge sees — it's the tangible evidence behind every claim in the pitch.

---

## What we are NOT building

- An AI shopping chatbot
- A Google-like product search engine
- A universal web scraper
- An AI with direct access to money

## What we ARE building

The infrastructure layer that makes a merchant ready for AI buyers — data in, structured Commerce Passport out, gated and audited transactions through Razorpay.

---

## Build order

| Phase | What | Why this order |
| --- | --- | --- |
| 1 | Merchant dashboard + data structuring + validation → Commerce Passport | Foundation everything else depends on |
| 2 | MCP tool layer + a simple scripted AI buyer client | Thin connector, low risk, needed before decision logic |
| 3 | Mandate Check | Highest-value, lowest-effort differentiator — build before it's needed downstream |
| 4 | Merchant rules + Policy Gate (rules-based, not ML) | Depends on Passport data; explainable by design |
| 5 | Razorpay checkout + Verification | Most external-dependency risk — sequence last, once everything feeding it is stable |
| — | Audit Log | Add incrementally at the end of every phase above, not as a separate final phase |
| 6 | Decision Receipt UI + demo script (happy path + one blocked path) | Polish once the pipeline works end to end |

**Explicitly deferred (stretch goals only, in this order if time remains):** autonomous LLM-driven AI buyer (upgrade from scripted client) → bounded generalization to common e-commerce templates → true ML-driven dynamic pricing (needs data you won't have in 2 weeks).

---

## Suggested stack (matches your existing tools)

- **Backend:** FastAPI
- **Frontend/dashboard:** React
- **LLM (decision engine, structuring):** Gemini
- **Payments:** Razorpay test-mode APIs
- **Agent protocol:** MCP tool exposure
- **Auth/logging patterns:** reuse your LowKey Secure approach for audit trail