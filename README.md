# Nexus Trader

AI-powered stock market research and options trading assistant.

Built on the Nexus AI engine extracted from Nexus Wellness — conversation memory, structured reasoning, tone analysis, and knowledge synthesis — retargeted for financial markets.

---

## Features

| Module | Description |
|---|---|
| **Visual Console** | Interactive price charts (candlestick + volume), support/resistance overlays, SMA lines, pattern annotations |
| **Nexus AI Chat** | Conversational assistant with market context injection, intent routing, and session memory |
| **Options Scanner** | Strategy suitability scorer, Black-Scholes Greeks calculator, delta/value sensitivity chart |
| **Backtester** | Historical long call/put simulation with equity curve, win rate, and trade log |
| **Watchlist** | Live quote tracking with change indicators |
| **Learn** | Options and technical analysis reference (Greeks, strategies, risk management) |

### AI Capabilities
- Technical analysis: RSI, MACD, Bollinger Bands, moving averages, volume
- Pattern recognition: Golden/Death Cross, Head & Shoulders, Double Top/Bottom, RSI divergence, BB squeeze
- Options analysis: Black-Scholes pricing, Greeks, IV rank, strategy scoring, unusual activity detection
- Backtesting: Historical options strategy simulation on up to 50 years of data
- Structured reasoning: Evidence-based signal synthesis with confidence scores

---

## Stack

**Backend** — Python / FastAPI
- `app/nexus_core/` — AI conversation engine, memory store, reasoning framework
- `app/services/market_data.py` — Polygon.io + Alpha Vantage data layer
- `app/services/pattern_recognition.py` — Chart pattern and technical signal detection
- `app/services/options_analysis.py` — Black-Scholes, Greeks, strategy scoring, backtesting
- `app/routers/` — REST endpoints: `/chat`, `/market`, `/options`, `/watchlist`

**Frontend** — Next.js 15 / TypeScript / Tailwind CSS
- Recharts for all visualizations (price charts, options charts, equity curves, radar)
- Dark terminal-style UI

---

## Quick Start

### 1. Clone and configure

```bash
cd nexus-trader

# Backend
cp backend/.env.example backend/.env
# Edit backend/.env — add your API keys (see below)

# Frontend
cp frontend/.env.example frontend/.env.local
```

### 2. Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Run the frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Docker (optional)

```bash
docker-compose up --build
```

---

## API Keys

The app works without any keys — the AI chat returns structured fallback responses and the engines run locally. To unlock full functionality:

| Key | Where to get | What it enables |
|---|---|---|
| `NEXUS_API_KEY` | [platform.openai.com](https://platform.openai.com) | Full AI chat responses (GPT-4o) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | Fast free AI fallback (Llama 3.3) |
| `POLYGON_API_KEY` | [polygon.io](https://polygon.io) | Real-time quotes, OHLCV history, options chains |
| `ALPHA_VANTAGE_API_KEY` | [alphavantage.co](https://www.alphavantage.co/support/#api-key) | Historical OHLCV + RSI/MACD/SMA (free: 25 req/day) |

**Recommended minimum setup:** `GROQ_API_KEY` (free) + `ALPHA_VANTAGE_API_KEY` (free) gives you full AI chat and historical chart data.

---

## API Reference

```
POST /api/v1/chat                          — AI conversation
GET  /api/v1/market/quote/{symbol}         — Current quote
GET  /api/v1/market/history/{symbol}       — Historical OHLCV (up to 50 years)
GET  /api/v1/market/analysis/{symbol}      — Quote + technicals + patterns + reasoning
GET  /api/v1/market/patterns/{symbol}      — Pattern recognition only
GET  /api/v1/options/chain/{symbol}        — Options chain with enriched Greeks
GET  /api/v1/options/unusual/{symbol}      — Unusual options activity
GET  /api/v1/options/strategies/{symbol}   — Strategy suitability scores
POST /api/v1/options/greeks                — Black-Scholes calculator
POST /api/v1/options/backtest              — Historical strategy backtest
GET  /api/v1/watchlist/{session_id}        — Watchlist with live quotes
```

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Disclaimer

**This software is for informational and educational purposes only. It does not constitute financial advice, investment advice, or a recommendation to buy or sell any security. Options trading involves substantial risk of loss and is not suitable for all investors. Past performance does not guarantee future results. Always conduct your own due diligence and consult a licensed financial advisor before making any investment decisions.**
