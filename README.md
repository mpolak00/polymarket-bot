# Polymarket Whale Tracker Bot

Monitors **@PredictionRadarBot** on Telegram for large ("whale") trades on
Polymarket and automatically copies them proportionally into your own wallet.

Optionally includes a **BTC Up/Down arbitrage scanner** that bets on Bitcoin
price direction when the outcome is nearly certain.

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

## What you need before starting

You need **4 things** to run this bot:

| # | What | Where to get it |
|---|------|-----------------|
| 1 | **Telegram API ID** (number) | https://my.telegram.org/apps → create app → copy `api_id` |
| 2 | **Telegram API Hash** (string) | Same page → copy `api_hash` |
| 3 | **Your phone number** | The number linked to your Telegram account, e.g. `+385601234567` |
| 4 | **Polygon wallet private key** | Your MetaMask/wallet private key starting with `0x` — this wallet must have USDC deposited on Polymarket |

> **Safety**: The bot starts in **DRY_RUN mode** by default — no real money is spent until you explicitly set `DRY_RUN=false`.

## Quick start

```bash
# 1. Run the setup script (creates venv, installs deps, creates .env)
bash setup.sh

# 2. Edit .env with your 4 credentials
nano .env

# 3. Run the bot (dry-run mode by default)
source .venv/bin/activate
python main.py
```

On **first run**, Telegram will send a verification code to your phone — enter it when prompted. This only happens once; after that, a session file is saved.

## Manual setup (if you prefer)

```bash
# 1. Create virtual environment (Python 3.10+ required)
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
nano .env   # fill in your 4 credentials

# 4. Run
python main.py
```

## Two ways to run

### Option A: Command-line bot
```bash
python main.py
```
Runs in your terminal with colored log output. Press `Ctrl+C` to stop.

### Option B: Web dashboard
```bash
python web_app.py
```
Open **http://localhost:5000** in your browser. Provides:
- Setup wizard (fill credentials in browser)
- Start/stop bot with a button
- Live log viewer
- Trade history and whale statistics

## Configuration

All settings are in `.env`. The only **required** ones are:

| Variable | Description |
|---|---|
| `TELEGRAM_API_ID` | From https://my.telegram.org/apps |
| `TELEGRAM_API_HASH` | From https://my.telegram.org/apps |
| `TELEGRAM_PHONE` | Your phone number with country code (`+385...`) |
| `POLYGON_PRIVATE_KEY` | Wallet private key (`0x...`) |

Everything else has safe defaults. Key **optional** settings:

| Variable | Default | Description |
|---|---|---|
| `DRY_RUN` | `true` | Simulate trades without spending money |
| `MAX_TRADE_SIZE_USDC` | 50 | Hard cap per trade in USDC |
| `MAX_TRADE_PCT` | 0.05 | Max % of balance per trade |
| `MIN_WHALE_SIZE_USDC` | 5000 | Ignore whale trades below this |
| `COPY_SCALE_FACTOR` | 0.001 | your\_bet = whale\_bet × factor |
| `MIN_PROBABILITY` | 0.05 | Skip markets below this prob |
| `MAX_PROBABILITY` | 0.95 | Skip markets above this prob |
| `MARKET_COOLDOWN_SECS` | 300 | Cooldown per market (seconds) |
| `MAX_TRADES_PER_HOUR` | 10 | Rate limit per hour |
| `MAX_DAILY_LOSS_USDC` | 500 | Daily spending cap |

### BTC Arbitrage (optional)

Set `BTC_ARB_ENABLED=true` to enable. See `.env.example` for all BTC arb settings.

## Going live (real trades)

1. Start with `DRY_RUN=true` (default) — verify signals parse correctly in logs
2. Make sure your wallet has USDC deposited on Polymarket
3. Set small limits first: `MAX_TRADE_SIZE_USDC=5` and `MAX_DAILY_LOSS_USDC=50`
4. Set `DRY_RUN=false` in `.env`
5. Restart the bot

## Troubleshooting

| Problem | Solution |
|---|---|
| `ERROR: Required environment variable 'TELEGRAM_API_ID' is not set` | Copy `.env.example` to `.env` and fill in your credentials |
| `FloodWaitError` on first run | Telegram rate limit — wait the indicated seconds and try again |
| `SessionPasswordNeededError` | Your Telegram has 2FA — enter the password when prompted |
| `py-clob-client not installed` | Run `pip install py-clob-client` in your venv |
| `Could not resolve market` | Market name didn't fuzzy-match — try lowering `FUZZY_MATCH_CUTOFF` |
| Bot connects but no trades | Check: is `@PredictionRadarBot` posting? Is `MIN_WHALE_SIZE_USDC` too high? |
| `Insufficient balance` | Deposit USDC to your wallet on Polymarket |

## File structure

```
├── main.py              # CLI entry point
├── web_app.py           # Web dashboard entry point
├── config.py            # Environment variable loader
├── telegram_monitor.py  # Telegram listener
├── trade_parser.py      # Message parser (regex-based)
├── portfolio_manager.py # Risk management & position sizing
├── market_resolver.py   # Maps questions → Polymarket markets
├── polymarket_trader.py # CLOB API order execution
├── btc_arb.py           # BTC Up/Down arbitrage scanner
├── btc_price_feed.py    # BTC price from Binance/Coinbase
├── bot_runner.py        # Thread wrapper for web integration
├── state.py             # Shared state between Flask and bot
├── logger.py            # Colored logging setup
├── setup.sh             # Quick setup script
├── .env.example         # Configuration template
├── templates/           # Flask HTML templates
└── requirements.txt     # Python dependencies
```

## Safety

- **Always start with `DRY_RUN=true`** to verify parsing is correct.
- Never commit your `.env` file – it is in `.gitignore`.
- The bot enforces hard dollar caps, probability filters, rate limits, and daily spending caps.
- This is not financial advice. Copying whale trades is inherently risky.
