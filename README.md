# Polymarket Whale Tracker Bot

Monitors **@PredictionRadarBot** on Telegram for large ("whale") trades on
Polymarket and automatically copies them proportionally into your own wallet.

## How it works

```
@PredictionRadarBot (Telegram)
        │
        ▼
  telegram_monitor.py   ← listens for new messages
        │
        ▼
  trade_parser.py       ← extracts market, outcome, size, probability
        │
        ▼
  portfolio_manager.py  ← applies risk filters & sizes your position
        │
        ▼
  market_resolver.py    ← maps free-text question → Polymarket conditionId/tokenId
        │
        ▼
  polymarket_trader.py  ← places limit order via CLOB API
```

## Prerequisites

- Python 3.10+
- A Telegram account (to receive messages from @PredictionRadarBot)
- A Polygon wallet funded with USDC (deposited on Polymarket)

## Setup

```bash
# 1. Clone and enter the directory
git clone <repo> && cd polymarket-bot

# 2. Create virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env with your credentials (see notes below)

# 5. Run (dry-run first!)
DRY_RUN=true python main.py
```

On first run Telethon will prompt for a verification code sent to your phone.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_API_ID` | — | From https://my.telegram.org/apps |
| `TELEGRAM_API_HASH` | — | From https://my.telegram.org/apps |
| `TELEGRAM_PHONE` | — | Your phone number (+country code) |
| `POLYGON_PRIVATE_KEY` | — | Wallet private key (keep secret!) |
| `MAX_TRADE_SIZE_USDC` | 50 | Hard cap per trade in USDC |
| `MAX_TRADE_PCT` | 0.05 | Max % of balance per trade |
| `MIN_WHALE_SIZE_USDC` | 5000 | Ignore whale trades below this |
| `COPY_SCALE_FACTOR` | 0.001 | your\_bet = whale\_bet × factor |
| `MIN_PROBABILITY` | 0.05 | Skip markets below this prob |
| `MAX_PROBABILITY` | 0.95 | Skip markets above this prob |
| `MARKET_COOLDOWN_SECS` | 300 | Cooldown per market (seconds) |
| `DRY_RUN` | true | Simulate without spending money |

## Safety

- **Always start with `DRY_RUN=true`** to verify parsing is correct.
- Never commit your `.env` file – it is in `.gitignore`.
- The bot enforces hard dollar caps and probability filters by default.
- This is not financial advice. Copying whale trades is inherently risky.
