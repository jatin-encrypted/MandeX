# MandeX — AI Commerce Gateway

> **Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

MandeX is a merchant-side infrastructure layer that makes merchants ready for AI buyers. It converts a merchant's commerce data into an AI-readable **Commerce Passport**, exposes it to AI agents through **MCP tools**, and lets those agents discover, decide, and purchase products through **Razorpay** — securely gated by explicit buyer mandates and merchant policies.

**Core Principle:** *"LLM proposes. Deterministic rules authorize. Razorpay executes."*

Every decision is explainable, every financial action is gated, and every transaction is strictly audited.

---

## 🎯 The Vision & Core Components

MandeX bridges the gap between autonomous AI shopping agents and traditional merchant stores. It provides:

1. **Commerce Passport:** A standardized, AI-readable profile of a merchant's catalog, inventory, and rules (discounts, margins, return policies).
2. **MCP Tool Layer:** An interface for AI agents to natively interact with the store (search catalog, build cart, check policy, checkout).
3. **Dual-Layer Authorization:**
   - **Buyer Mandate:** A cryptographic authorization (signed via HMAC-SHA256) where a human buyer sets limits (max amount, expiry, categories) for their AI agent.
   - **Merchant Policy Gate:** A strict, deterministic engine enforcing the merchant's rules (stock availability, minimum margins, max AI discount, manual approval thresholds).
4. **Razorpay Verification Lifecycle:** Server-side recalculation and HMAC callback verification ensure no price tampering occurs between AI selection and final payment.
5. **Decision Receipts & Audit Log:** An immutable ledger of every AI action, policy check, and payment attempt for full transparency.

---

## 🚀 Quick Start

### 1. Backend Setup

The backend is built with FastAPI, SQLite, and SQLAlchemy.

```bash
cd backend
cp .env.example .env          # Fill in your Razorpay and Gemini API keys
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Seed Demo Data

Run the seeding script to populate the database with a test merchant, 8 products (shoes & apparel), and a cryptographic demo mandate.

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python seed_demo.py
# ⚠️ Note the MERCHANT_ID and MANDATE_ID printed at the end of this script!
```

### 3. Frontend Setup

The frontend is a React 19 + TypeScript + Vite app using TailwindCSS.

```bash
cd frontend
cp .env.example .env          # Fill in Firebase config and the IDs from step 2
npm install
npm run dev
```

### 4. Run Tests

The backend has a comprehensive pytest suite (53/53 passing tests) covering security, intent parsing, mandate cryptography, and Razorpay flows.

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

---

## 🕹️ Running the AI Buyer Demo

The primary interactive demo lives at `http://localhost:5173/buyer-demo`. It executes a simulated agent shopping flow using the seeded data. 

**Path A: The Happy Path (Approved)**
1. Prompt: *"Find me running shoes under ₹6,000"*
2. The AI searches the catalog, picks the best match within budget (e.g., Velocity Pro Running Shoes), and builds a cart.
3. The cart total passes the buyer's ₹6,000 mandate.
4. The merchant's stock and margin policies pass.
5. Razorpay Test Checkout opens. You complete the payment.
6. A **Verified Decision Receipt** is issued.

**Path B: The Blocked Path (Denied by Mandate)**
1. Prompt: *"Buy the ₹8,999 version instead"*
2. The AI specifically selects the SprintX Track Spikes.
3. The cart total exceeds the buyer's ₹6,000 mandate.
4. The Mandate Check fails immediately.
5. The checkout flow terminates. **Razorpay is never called.**
6. A **Blocked Decision Receipt** is issued explaining the limit breach.

*You can view the cryptographic audit trail of both transactions in the "Audit Log" tab of the Merchant Dashboard.*

---

## 🏗️ Architecture & Flow

```text
┌───────────────────────────────────────────────────────────┐
│  FRONTEND  (React 19 + TypeScript + Vite + TailwindCSS)    │
│  /buyer-demo  →  DemoBuyerConsole.tsx (The AI Buyer)       │
│  /dashboard   →  Merchant Dashboard (Firebase Auth)        │
└─────────────────────────┬──────────────────────────────────┘
                          │  HTTP (localhost:8000)
┌─────────────────────────▼──────────────────────────────────┐
│  BACKEND  (FastAPI + SQLAlchemy + SQLite)                   │
│                                                             │
│  MCP Handlers: /mcp/search_catalog, /mcp/checkout, etc.    │
│                                                             │
│  Services:                                                  │
│   - Mandate Service (HMAC signing & expiry/limit checks)   │
│   - Policy Service (Stock, margins, discount limits)       │
│   - Razorpay Service (Idempotent order creation)           │
│   - Verification Service (HMAC callback verification)      │
│   - Audit Service (Immutable event ledger)                 │
└─────────────────────────┬──────────────────────────────────┘
             ┌────────────┴──────────────┐
        Razorpay API              Gemini API
        (Test Mode)               (CLI buyer intent)
```

### The Model Context Protocol (MCP) Tools

MandeX exposes standard tools that any MCP-compliant agent can use to interact with the merchant:

| Tool | Purpose |
|---|---|
| `search_catalog` | Discover products across the merchant's active Commerce Passport. |
| `get_product` | Retrieve exact details and stock for a specific SKU. |
| `build_cart` | Lock in item selections and generate an idempotency key. |
| `check_policy` | Run the dual-layer Mandate & Policy check to simulate the decision. |
| `checkout` | Finalize the decision, recalculate totals server-side, and invoke Razorpay if approved. |

*(Note: The frontend demo hits the FastAPI `/mcp/*` HTTP endpoints directly to seamlessly integrate the UI, while a standalone Python CLI client in `ai_buyer_client/buyer.py` uses the standard stdio MCP server bridge).*

---

## 🔒 Security & Constraints

MandeX is built with strict financial safeguards:
- **No Price Tampering:** The frontend never dictates the final price. The backend recalculates the total from the authoritative database (`gateway.db`) right before invoking Razorpay.
- **Server-Side Verification:** `payment_verified` status is strictly gated behind Razorpay's HMAC-SHA256 signature callback verification in the backend.
- **Razorpay Isolation:** The Razorpay `order.create()` API is physically unreachable in the code if `final_decision == "BLOCK"`.
- **Cross-Merchant Safety:** Carts are scoped to specific merchant IDs at creation; an agent cannot build a cart for Merchant A and check it out against Merchant B's policy.
