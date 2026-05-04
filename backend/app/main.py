"""Nexus Trader — FastAPI application entry point."""
from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.routers import chat, market, options, watchlist

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise persistent memory DB (creates tables if missing)
    from app.db.database import init_db
    await init_db()
    log.info("nexus_trader.startup", extra={"environment": settings.environment})
    yield
    log.info("nexus_trader.shutdown")


app = FastAPI(
    title="Nexus Trader API",
    description="AI-powered stock market research and options trading assistant.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins + ["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.(gitpod|gitpod\.dev|ona\.dev).*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Routers ───────────────────────────────────────────────────────────────────

API = "/api/v1"
app.include_router(chat.router, prefix=API)
app.include_router(market.router, prefix=API)
app.include_router(options.router, prefix=API)
app.include_router(watchlist.router, prefix=API)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", tags=["system"])
async def root():
    return {
        "name": "Nexus Trader API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "POST /api/v1/chat",
            "GET  /api/v1/market/quote/{symbol}",
            "GET  /api/v1/market/history/{symbol}",
            "GET  /api/v1/market/analysis/{symbol}",
            "GET  /api/v1/market/patterns/{symbol}",
            "GET  /api/v1/options/chain/{symbol}",
            "GET  /api/v1/options/unusual/{symbol}",
            "GET  /api/v1/options/strategies/{symbol}",
            "POST /api/v1/options/greeks",
            "POST /api/v1/options/backtest",
            "GET  /api/v1/watchlist/{session_id}",
        ],
    }
