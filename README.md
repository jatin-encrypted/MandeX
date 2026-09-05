# MandeX

**Razorpay AI Buildathon · Track 01 — AI Growth & Agentic Commerce**

Most online stores are built for people who can read a page, squint at a price, and click "buy." An AI agent can't do that reliably — it can't tell if "₹4,999 onwards" means anything, and it definitely shouldn't be guessing with someone else's money. MandeX is the layer in between: it takes a merchant's catalog and rules, turns them into something an agent can actually reason over, and lets that agent shop and pay through Razorpay — without ever getting more authority than it was given.

The whole system runs on one rule:

> **The LLM proposes. Deterministic rules authorize. Razorpay executes.**

Nothing gets charged because a model felt confident about it.

---

## What's actually in here

An agent talking to MandeX gets five things to work with, and nothing else:

| Piece | What it does |
|---|---|
| **Commerce Passport** | The merchant's catalog, stock, and rules, structured so an agent can read them without guessing |
| **MCP tools** | `search_catalog`, `get_product`, `build_cart`, `check_policy`, `checkout` — the only five moves an agent can make |
| **Buyer Mandate** | An HMAC-signed limit a human sets for their agent — max spend, allowed categories, an expiry. If the mandate doesn't cover it, the agent doesn't buy it |
| **Policy Gate** | The merchant's own rules — stock, minimum margin, discount ceiling, manual-approval threshold — checked separately from the mandate, not folded into it |
| **Audit log** | Every check, decision, and payment attempt, written down as it happens, not reconstructed after |

Mandate and Policy are kept as two genuinely separate checks on purpose. An agent can have every right to spend and still get blocked because the merchant's margin rule says no — those are different failures, and the log should say which one actually happened.

---

## How a purchase actually moves through it

Say an agent gets told: *"find me running shoes under ₹6,000."*

1. It calls `search_catalog`, gets back what's actually in stock, picks a match.
2. `build_cart` locks the selection in and stamps it with an idempotency key, so a retried request can't double-charge anyone.
3. `check_policy` runs the mandate check, then the policy gate, independently. Either can fail on its own.
4. If both clear, `checkout` recalculates the total server-side — the price the agent saw is never the price that gets charged without a fresh check — and hands off to Razorpay.
5. Razorpay confirms the payment via HMAC callback. Only then does the receipt say "verified."
6. If either check fails, the flow stops before Razorpay is ever called. Not declined — never invoked.

That last part is the whole point of the project. A blocked purchase should be provably blocked, not just told-you-it-was.

```
FRONTEND (React 19 + TypeScript + Vite + Tailwind)
  /buyer-demo → DemoBuyerConsole.tsx   (the AI buyer)
  /dashboard  → Merchant Dashboard      (Firebase Auth)
        │
        │ HTTP → localhost:8000
        ▼
BACKEND (FastAPI + SQLAlchemy + SQLite)
  /mcp/search_catalog, /mcp/checkout, etc.

  mandate_service   — HMAC signing, limit + expiry checks
  policy_service    — stock, margin, discount, approval threshold
  razorpay_service  — idempotent order creation
  verification_service — HMAC callback verification
  audit_service     — append-only event log
        │
   ┌────┴─────┐
Razorpay API   Gemini API
(test mode)    (buyer intent parsing)
```

---

## Running it

**Backend** — FastAPI, SQLite, SQLAlchemy.

```bash
cd backend
cp .env.example .env          # fill in your Razorpay and Gemini keys
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Seed demo data** — one merchant, eight products (shoes and apparel), one signed demo mandate.

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python seed_demo.py
# copy the MERCHANT_ID and MANDATE_ID it prints — the frontend needs them
```

**Frontend** — React 19 + TypeScript + Vite + Tailwind.

```bash
cd frontend
cp .env.example .env          # Firebase config + the IDs from the step above
npm install
npm run dev
```

**Tests** — 53/53 passing as of this build. Covers mandate cryptography, policy logic, intent parsing, and the Razorpay flow.

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

---

## Watching it actually work

Open `http://localhost:5173/buyer-demo`. Two scripted paths, same demo mandate (₹6,000 limit):

**The happy path.**
Type *"find me running shoes under ₹6,000."* The agent searches, lands on the Velocity Pro Running Shoes, builds a cart, and both the mandate check and the policy checks pass. Razorpay's test checkout opens, you pay, and a verified receipt comes back.

**The blocked path.**
Type *"buy the ₹8,999 version instead."* The agent picks the SprintX Track Spikes — ₹8,999, over the ₹6,000 mandate. The check fails immediately. Checkout stops there. Razorpay is never called. The receipt explains exactly why, in the same format as an approved one.

Both runs — full cryptographic trail included — show up in the Audit Log tab of the merchant dashboard.

---

## The MCP tools, if you're integrating your own agent

| Tool | Purpose |
|---|---|
| `search_catalog` | Search a merchant's active Commerce Passport |
| `get_product` | Pull stock and details for one SKU |
| `build_cart` | Lock in a selection, generate the idempotency key |
| `check_policy` | Run the mandate check and the policy gate, report both |
| `checkout` | Recalculate server-side, call Razorpay only on approval |

The frontend demo talks to these directly over HTTP at `/mcp/*` — that's a shortcut for the UI. A real MCP client (`ai_buyer_client/buyer.py`) talks to the same tools over the standard stdio bridge, if you want to point your own agent at it instead of ours.

---

## Why it's hard to abuse

- **The frontend never sets the price.** Whatever it shows is recalculated from the database, server-side, the instant before Razorpay is called. Nothing the client sends is trusted.
- **"Verified" means Razorpay said so.** `payment_verified` only gets set after the backend checks Razorpay's own HMAC-SHA256 signature on the callback — not because the frontend said the popup closed.
- **A blocked cart can't reach Razorpay.** Not "we choose not to call it" — the code path to `order.create()` is unreachable once `final_decision` is `BLOCK`.
- **Carts don't cross merchants.** A cart is scoped to the merchant it was built against at creation. An agent can't build against one store and check out against another.

---

## What this isn't

No ML-driven pricing — the rules engine is deterministic on purpose, because "explainable" was the actual bar, not "impressive." No scraping arbitrary websites — merchants type their catalog in or upload it; there's nothing to infer, so nothing to get wrong. No fully autonomous shopping agent — the buyer console is a demo harness that proves the gateway works, not a general-purpose product. We built the layer that makes a merchant transactable by an AI buyer, not the AI buyer itself.

Field names and structure loosely track what ACP and AP2 are shaping up to look like — checkout as a session, mandate as a signed scope — because building toward where the ecosystem is clearly headed seemed better than inventing something unrecognizable. None of it claims actual compliance with either spec. The mandate signature is a real HMAC check, not a verifiable credential — said plainly, so nobody has to find that out the hard way in a Q&A.