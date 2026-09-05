from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.session import engine
from app.db import models
from app.routers import merchant, mcp_tools, receipts

# Create all DB tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Commerce Gateway",
    description="Merchant-side infrastructure for AI buyers. Built for Razorpay AI Buildathon.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(merchant.router)
app.include_router(mcp_tools.router)
app.include_router(receipts.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Commerce Gateway"}
