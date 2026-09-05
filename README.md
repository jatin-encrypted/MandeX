# MandeX — AI Commerce Gateway

> **Razorpay AI Buildathon — Track 01: AI Growth & Agentic Commerce**

AI Commerce Gateway is a merchant-side infrastructure layer that converts a merchant's commerce data into an AI-readable **Commerce Passport**, exposes it to AI agents through **MCP tools**, and lets those agents discover, decide, and purchase products through **Razorpay** — within explicit buyer (mandate) and merchant (policy) limits. Every decision is explainable, every financial action is gated, and every transaction is audited.

---

## Quick Start

### 1. Backend

```bash
cd backend
cp .env.example .env          # fill in your API keys
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Seed demo data

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. python seed_demo.py
# Note the MERCHANT_ID and MANDATE_ID printed at the end
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env          # fill in Firebase config + paste demo IDs
npm install
npm run dev
```

### 4. Run tests

```bash
cd backend
source venv/bin/activate
PYTHONPATH=. pytest tests/ -v
```

---

## Demo Script

1. Open `http://localhost:5173/demo`
2. Paste the `MERCHANT_ID` and `MANDATE_ID` from the seed step (or use `.env` pre-fill)
3. Click **Happy path** → run → see APPROVED receipt + Razorpay order
4. Click **Blocked path** → run → see BLOCKED receipt with reason + "Razorpay was never called"
5. Open the Merchant Dashboard → Audit Log → see both events

---

## Architecture

```
Merchant → uploads catalog → Commerce Passport (validated, activated)
                                     ↓
                           MCP Tool Layer (5 tools)
                                     ↓
                           AI Buyer states intent
                                     ↓
                           Decision Engine (Gemini)
                                     ↓
                      Mandate Check → Policy Gate
                       ↙ APPROVE         BLOCK ↘
                  Razorpay →            Explanation
                  Verification          (Razorpay never called)
                       ↘                    ↙
                          Audit Log + Decision Receipt
```

## MCP Tools

| Tool | Description |
|---|---|
| `search_catalog` | Filter + keyword match over active passport |
| `get_product` | Fetch a single product by ID |
| `build_cart` | Build a cart with optional upsell |
| `check_policy` | Run Mandate Check then Policy Gate |
| `checkout` | session_create → session_update → session_complete |

## Stack

- **Backend:** FastAPI + SQLite + SQLAlchemy
- **Frontend:** React 19 + TypeScript + TailwindCSS (Vite)
- **Auth:** Firebase Auth
- **Payments:** Razorpay Orders API (test mode only)
- **Agent Protocol:** MCP Python SDK
- **AI Reasoning:** Gemini API (buyer intent parsing only)

## Environment Variables

See `backend/.env.example` and `frontend/.env.example`.

**Never commit `.env` files with real keys.**
