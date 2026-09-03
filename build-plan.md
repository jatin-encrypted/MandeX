# AI Commerce Gateway — Engineering Build Plan

**Purpose of this document:** a complete, unambiguous handoff spec for an AI coding agent (Claude Code, Codex, etc.) to implement this project without needing to make product decisions on its own. Every decision that could be ambiguous has been made explicit below. If something isn't covered here, the agent should stop and ask rather than guess.

---

## 0. Hard Constraints — Read First

These are non-negotiable. Do not deviate from these even if a "better" approach seems obvious mid-build.

1. **Razorpay TEST MODE keys only.** Never wire in live keys. All payment flows run against Razorpay's test environment.
2. **No ML-driven dynamic pricing.** Pricing/discount logic is a deterministic rules engine (if/else over merchant-configured thresholds). Do not add a model, a scoring function, or "smart" pricing logic beyond simple rule evaluation.
3. **No automatic website scraping/extraction (Mode 2) in this build.** Merchant data enters the system only via the dashboard form or a structured file upload (CSV/JSON). Do not build a web scraper, do not add an "extraction confidence" system — none is needed because the merchant is the data source.
4. **No fully autonomous, freeform AI Buyer.** The "AI Buyer" is a scripted or lightly LLM-assisted client that calls the MCP tools in a bounded way to demonstrate the flow. It is a demo harness, not a general-purpose shopping agent product.
5. **Mandate Check and Policy Gate are two distinct internal checks**, even if the UI/receipt presents them as one moment. Do not merge their logic into a single function — keep them as separate, independently testable modules.
6. **Every state-changing action must write an audit log entry.** If a code path can approve, block, charge, or refund, it must log before returning.
7. **Frontend must not look AI-generated.** See Section 6 (Design System) — follow it exactly. No purple/lavender gradients, no generic rounded SaaS card kit, no tracked-out ALL-CAPS eyebrows, no arrow-suffixed buttons, no soft grey box-shadow on every card.

---

## 1. Product Summary

**AI Commerce Gateway** — a merchant-side infrastructure layer that converts merchant-provided commerce data into a structured **Commerce Passport**, exposes it to AI agents via **MCP tools**, and lets those agents discover, decide, and purchase products through **Razorpay** — within explicit buyer (mandate) and merchant (policy) limits. Every decision is explainable, every financial action is gated, and every transaction is audited.

Built for: Razorpay AI Buildathon, Track 01 (AI Growth & Agentic Commerce).

**We are building:** the layer that makes a merchant ready for AI buyers.
**We are NOT building:** a shopping chatbot, a search engine, a universal scraper, or an AI with unbounded access to money.

---

## 2. Tech Stack

Chosen to match the builder's existing stack (fast to build, no new-tool learning curve mid-hackathon).

| Layer | Choice | Notes |
|---|---|---|
| Backend | **FastAPI** (Python 3.11+) | Async, matches prior projects (PrivaScore, LowKey Secure) |
| Database | **SQLite** for the hackathon build | Zero-ops; swap for Postgres only if time allows — do not spend time on this swap unless core features are done |
| Frontend | **React 19 + TypeScript + TailwindCSS** | Matches prior projects; Vite as the build tool |
| Auth | **Firebase Auth** (merchant dashboard login) | Reuse pattern from LowKey Secure / Artisans GenAI |
| Payments | **Razorpay Orders API** (test mode) | `razorpay` Python SDK on backend; never call Razorpay directly from frontend |
| Agent protocol | **MCP (Model Context Protocol)**, official Python SDK | Backend exposes tools; a small client script acts as the AI Buyer |
| AI Buyer's reasoning | **Gemini API** (function-calling / tool-use mode) | Only used to interpret buyer intent into structured search params — not for anything else |
| Deployment (optional, if time allows) | Backend on Render/Fly.io, frontend on Vercel | Not required for a local/localhost demo; don't spend hackathon time on this unless everything else is done |

---

## 3. Repository Structure

```
ai-commerce-gateway/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint
│   │   ├── config.py                # env vars, settings
│   │   ├── db/
│   │   │   ├── models.py            # SQLAlchemy models
│   │   │   └── session.py
│   │   ├── schemas/                 # Pydantic request/response models
│   │   │   ├── passport.py
│   │   │   ├── mandate.py
│   │   │   ├── cart.py
│   │   │   ├── policy.py
│   │   │   └── receipt.py
│   │   ├── services/
│   │   │   ├── passport_service.py      # Commerce Passport CRUD + validation
│   │   │   ├── mandate_service.py       # buyer authority checks
│   │   │   ├── policy_service.py        # merchant rule checks (Policy Gate)
│   │   │   ├── razorpay_service.py      # order creation, payment capture
│   │   │   ├── verification_service.py  # post-payment quoted-vs-charged check
│   │   │   └── audit_service.py         # append-only logging
│   │   ├── routers/
│   │   │   ├── merchant.py          # dashboard-facing REST endpoints
│   │   │   ├── mcp_tools.py         # MCP tool definitions (see Section 5)
│   │   │   └── receipts.py          # Decision Receipt retrieval
│   │   └── mcp_server.py            # MCP server wiring
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── MerchantOnboarding.tsx
│   │   │   ├── MerchantDashboard.tsx
│   │   │   ├── DecisionReceiptView.tsx
│   │   │   └── DemoBuyerConsole.tsx     # lets a judge trigger the AI Buyer live
│   │   ├── components/
│   │   ├── styles/
│   │   │   └── tokens.css               # design tokens from Section 6
│   │   └── lib/api.ts
│   └── package.json
├── ai_buyer_client/
│   └── buyer.py                     # scripted/LLM-assisted MCP client for demos
└── README.md
```

---

## 4. Data Models

Define these as Pydantic schemas (backend) and mirrored TypeScript types (frontend). Field names below are final — do not rename.

### 4.1 CommercePassport
```python
class Product(BaseModel):
    id: str
    name: str
    price_inr: float
    stock: int
    category: str
    description: str
    return_policy: str

class MerchantRules(BaseModel):
    max_ai_discount_pct: float          # e.g. 10.0
    min_margin_pct: float               # e.g. 20.0
    ai_upsell_enabled: bool
    preferred_categories: list[str]
    require_approval_above_inr: float   # e.g. 5000.0

class CommercePassport(BaseModel):
    merchant_id: str
    products: list[Product]
    rules: MerchantRules
    status: Literal["draft", "active"]
    created_at: datetime
    activated_at: datetime | None
```

### 4.2 Mandate (buyer-side authority)
```python
class Mandate(BaseModel):
    mandate_id: str
    buyer_id: str
    max_amount_inr: float
    allowed_categories: list[str]
    expires_at: datetime
    issued_at: datetime
```

### 4.3 Cart / Checkout
```python
class CartItem(BaseModel):
    product_id: str
    quantity: int
    unit_price_inr: float

class Cart(BaseModel):
    cart_id: str
    merchant_id: str
    mandate_id: str
    items: list[CartItem]
    upsell_items: list[CartItem]
    total_inr: float
```

### 4.4 PolicyDecision
```python
class PolicyDecision(BaseModel):
    cart_id: str
    mandate_check_passed: bool
    mandate_check_reason: str
    policy_check_passed: bool
    policy_check_reason: str
    final_decision: Literal["APPROVE", "BLOCK"]
    decided_at: datetime
```

### 4.5 DecisionReceipt
```python
class DecisionReceipt(BaseModel):
    receipt_id: str
    cart_id: str
    customer_request: str
    products_considered: int
    selected_product: Product
    selection_reasons: list[str]
    upsell_product: Product | None
    upsell_reason: str | None
    final_total_inr: float
    mandate_check_passed: bool
    payment_status: Literal["not_attempted", "verified", "failed"]
    razorpay_order_id: str | None
    blocked_reason: str | None
```

### 4.6 AuditLogEntry
```python
class AuditLogEntry(BaseModel):
    log_id: str
    event_type: Literal[
        "passport_activated", "mandate_checked", "policy_decided",
        "payment_attempted", "payment_verified", "payment_mismatch"
    ]
    merchant_id: str
    cart_id: str | None
    payload: dict          # event-specific details
    timestamp: datetime
```

---

## 5. MCP Tool Layer

Expose exactly these five tools. Do not add extra tools without checking in first.

| Tool | Input | Output | Notes |
|---|---|---|---|
| `search_catalog` | `{merchant_id, query, max_price}` | `list[Product]` | Simple filter + keyword match; no ML ranking needed |
| `get_product` | `{merchant_id, product_id}` | `Product` | |
| `build_cart` | `{merchant_id, mandate_id, product_id, quantity}` | `Cart` | Also runs upsell logic if `ai_upsell_enabled` |
| `check_policy` | `{cart_id}` | `PolicyDecision` | Runs Mandate Check then Policy Gate, in that order |
| `checkout` | `{cart_id}` | `DecisionReceipt` | Only proceeds to Razorpay if `PolicyDecision.final_decision == "APPROVE"` |

**Execution order inside `checkout`:** re-verify `check_policy` result → if APPROVE, call `razorpay_service.create_and_capture_order()` → call `verification_service.verify()` → write audit log → return `DecisionReceipt`. If BLOCK, skip Razorpay entirely, write audit log with reason, return `DecisionReceipt` with `blocked_reason` populated.

---

## 6. Design System — Read Carefully, This Prevents the "AI Slop" Look

The product's core artifacts — the **Commerce Passport** and the **Decision Receipt** — are literally passport/ticket/receipt documents. Lean into that as the visual language instead of generic dashboard-card design. This is the one place to spend visual boldness; keep everything else quiet.

### 6.1 Color tokens

```css
:root {
  --ink:        #14171A;  /* app shell background — desaturated near-black, NOT pure #0B0B0B */
  --ink-raised: #1D2125;  /* panels/nav on top of ink */
  --paper:      #EFEEE7;  /* the "physical document" surface — receipts, passport cards */
  --paper-line: #D9D6C9;  /* dividers/perforation on paper surfaces */
  --text-ink:   #F4F2EA;  /* text on dark ink background */
  --text-paper: #1C1B18;  /* text on paper background */
  --gold:       #C9A46A;  /* accent — passport foil / stamp gold. Use sparingly: badges, active states, key numbers */
  --verified:   #3E7A54;  /* APPROVE / verified state — deep forest green, not neon */
  --blocked:    #B8433D;  /* BLOCK / denied state — brick/stamp red, not alarm red */
}
```

**Explicitly forbidden:** any purple/violet/lavender hex, any gradient background, `#0B0B0B`/`#111` as "black", bright neon green or vermilion accents.

### 6.2 Typography

- **Headings & UI labels:** Space Grotesk (or similar grotesk sans) — confident, slightly technical, not the default Inter-everywhere look.
- **All numeric/data content** (prices, mandate limits, order IDs, timestamps, receipt line items): **IBM Plex Mono**. This is a deliberate choice, not decoration — receipts and boarding passes are traditionally printed in monospace/dot-matrix digits, so this reinforces the product's own metaphor.
- Two typefaces total. No third "display" font.
- Body line length under 80 characters.

### 6.3 The signature visual moment: paper-on-ink

The **Decision Receipt** and **Commerce Passport** render as light `--paper` cards floating on the dark `--ink` app shell — the literal contrast of holding a printed document under a dim screen. This is the one bold, memorable device in the whole product. Implementation notes:
- Top edge of paper cards uses a torn/perforated look (CSS `clip-path` with a repeating jagged or scalloped edge, or a dashed `--paper-line` rule with small circular cutouts) — not a rounded corner.
- No drop shadow soup — one soft, low-opacity shadow max, only on the paper card itself, nothing else.
- APPROVE state: thin `--verified` green rule + a small stamped badge, rotated 2–3° like a real stamp. BLOCK state: same treatment in `--blocked` red.

### 6.4 Layout

- **Merchant dashboard:** left-nav (fixed, `--ink-raised` background) + content area. Data tables use monospace for numeric columns. No card-grid dashboard — use dense, real tables; this is a B2B tool, not a consumer app.
- **Decision Receipt view / Demo Buyer Console:** single-column, centered, max-width ~480px — mimics looking at an actual receipt/boarding pass on a phone.
- Alignment: left-aligned throughout (this is a data/utility product, not an editorial page — do not center-align body content).

### 6.5 Explicitly avoid (generic AI-tell checklist)

- ❌ Purple/lavender anything
- ❌ Identical rounded-corner cards with the same soft grey shadow everywhere
- ❌ Tracked-out ALL-CAPS eyebrow labels above every section
- ❌ Buttons with a trailing "→"
- ❌ Meta text joined with middle dots ("A · B · C")
- ❌ Numbered 01/02/03 markers unless the content is a genuine sequence (the build phases ARE a sequence — fine to number those; features are NOT a sequence — don't number them)
- ❌ Scattered fade-in-on-scroll animation on every section. One orchestrated motion moment is allowed (e.g., the receipt "stamping" in when a decision resolves) — nothing else animates on load.

### 6.6 Voice

Plain, active, sentence case. Buttons say exactly what happens ("Activate passport," not "Submit"). Errors state what happened and what to do, without apologizing or being vague. Empty states are an invitation to act, not a mood.

---

## 7. Build Phases (in dependency order — build in this order, not diagram order)

Each phase has a Definition of Done (DoD). Do not start a phase until the previous one's DoD is met.

### Phase 1 — Merchant Dashboard + Commerce Passport
- Merchant signup/login (Firebase Auth)
- Onboarding form: catalog upload (CSV/JSON) or manual product entry
- Rules configuration form (max discount, min margin, upsell toggle, preferred categories, approval threshold)
- Structural validation on save (e.g., reject if price < cost implied by margin rule, reject missing required fields) — **this replaces the AI confidence system; it is a simple schema/range check, not an LLM call**
- "Activate for AI buyers" action → `CommercePassport.status = "active"`
- **DoD:** a merchant can create an account, enter a catalog + rules, and activate a passport. Passport data is retrievable via a backend endpoint.

### Phase 2 — MCP Tool Layer + Scripted AI Buyer
- Implement `search_catalog`, `get_product`, `build_cart` (upsell logic stubbed to "always suggest cheapest complementary item in a different category" for now)
- Build `ai_buyer_client/buyer.py` — takes a plain-text intent string, calls Gemini to extract `{query, max_price}`, calls `search_catalog`, picks top match, calls `build_cart`
- **DoD:** running the buyer script against an active passport returns a built cart end to end, no manual API calls needed.

### Phase 3 — Mandate Check
- `Mandate` creation (can be a simple hardcoded/demo-seeded mandate for now — no need for a full buyer-side UI)
- `mandate_service.check(cart, mandate)` — validates amount, category, expiry
- **DoD:** a cart exceeding the mandate's `max_amount_inr` or wrong category is rejected with a specific reason string; a valid cart passes.

### Phase 4 — Policy Gate
- `policy_service.check(cart, passport.rules)` — validates stock, margin floor, discount limits, approval threshold
- Combine with mandate check inside `check_policy` MCP tool, preserving them as separate function calls internally (see Constraint #5)
- **DoD:** `check_policy` returns a `PolicyDecision` with both sub-checks' results and a correct final APPROVE/BLOCK.

### Phase 5 — Razorpay Checkout + Verification
- `razorpay_service.create_and_capture_order()` using test-mode keys
- `verification_service.verify()` — compares the cart's quoted total against what Razorpay confirms was charged
- Wire into the `checkout` MCP tool per the execution order in Section 5
- **DoD:** an approved cart completes a real test-mode Razorpay payment and returns a `DecisionReceipt` with `payment_status = "verified"`.

### Phase 6 — Audit Log (build incrementally — should already be mostly done by now)
- Confirm every service from Phases 1–5 writes an `AuditLogEntry` at its decision point
- Simple merchant-facing audit/transaction table in the dashboard (read-only list, mono font for IDs/amounts)
- **DoD:** every APPROVE, BLOCK, payment, and verification event for a demo run is visible in the audit log, in order, with correct payloads.

### Phase 7 — Decision Receipt UI + Demo Console
- `DecisionReceiptView.tsx` — renders per Section 6.3 (paper-on-ink, torn edge, stamp badge)
- `DemoBuyerConsole.tsx` — a simple page where a judge can type a request (e.g., "running shoes under ₹6,000" then "buy the ₹8,999 version") and watch it resolve live, showing both the APPROVE and BLOCK cases
- **DoD:** both scripted demo scenarios (Section 8) run correctly through the actual UI, not just the API.

### Phase 8 — Demo Polish
- Seed 1–2 realistic demo merchants with clean catalogs
- Rehearse the exact 3-minute walkthrough (Section 8)
- **DoD:** the full happy-path + BLOCKED-case demo runs start to finish without manual database edits.

---

## 8. Required Demo Script (acceptance criteria for the whole build)

This is the actual test of "does the project work" — the agent should be able to run this end to end after Phase 7:

1. Judge types: *"Find me running shoes under ₹6,000."*
2. System returns a Decision Receipt: product selected, reasons shown, upsell shown, mandate check passed, payment verified.
3. Judge types: *"Buy the ₹8,999 version instead."*
4. System returns a BLOCKED receipt: reason = mandate limit exceeded, and **Razorpay was never called** (verify this is actually true in the backend logs, not just claimed in the UI).
5. Judge opens the merchant dashboard audit log and sees both events listed with correct detail.

If any of these five steps fails, the build is not done — this takes priority over any stretch feature.

---

## 9. Explicit Non-Goals for This Build

Do not implement these unless every phase above is done with time to spare:

- Automatic website scraping (Mode 2)
- ML-based dynamic pricing
- Fully autonomous/general-purpose AI Buyer
- Multi-merchant marketplace features
- Production deployment / CI/CD
- Payment methods beyond Razorpay test-mode cards/UPI simulation

---

## 10. Environment Variables (backend `.env`)

```
RAZORPAY_KEY_ID=<test mode key id>
RAZORPAY_KEY_SECRET=<test mode key secret>
GEMINI_API_KEY=<for ai_buyer_client only>
FIREBASE_PROJECT_ID=<merchant auth>
DATABASE_URL=sqlite:///./gateway.db
```

Never commit this file. Provide a `.env.example` with placeholder values instead.
