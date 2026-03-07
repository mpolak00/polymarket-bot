"""
Configuration loader – reads all settings from environment variables / .env file.
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_API_ID: int = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH: str = os.environ["TELEGRAM_API_HASH"]
TELEGRAM_PHONE: str = os.environ["TELEGRAM_PHONE"]          # e.g. +38160...
WHALE_BOT_USERNAME: str = os.getenv("WHALE_BOT_USERNAME", "PredictionRadarBot")
TELEGRAM_SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "polymarket_watcher")

# ── Polymarket / Polygon ───────────────────────────────────────────────────────
POLYGON_PRIVATE_KEY: str = os.environ["POLYGON_PRIVATE_KEY"]   # 0x-prefixed
CLOB_API_URL: str = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
GAMMA_API_URL: str = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# ── Trading parameters ─────────────────────────────────────────────────────────
# Maximum USDC to allocate per single copied trade
MAX_TRADE_SIZE_USDC: float = float(os.getenv("MAX_TRADE_SIZE_USDC", "50"))
# Max percentage of total wallet balance to use per trade (safety cap)
MAX_TRADE_PCT: float = float(os.getenv("MAX_TRADE_PCT", "0.05"))   # 5 %
# Minimum whale trade size to bother copying (filter noise)
MIN_WHALE_SIZE_USDC: float = float(os.getenv("MIN_WHALE_SIZE_USDC", "5000"))
# Scaling factor: your bet = whale_bet * COPY_SCALE_FACTOR (capped by limits above)
COPY_SCALE_FACTOR: float = float(os.getenv("COPY_SCALE_FACTOR", "0.001"))
# Minimum implied probability to accept a trade (skip near-certain / junk odds)
MIN_PROBABILITY: float = float(os.getenv("MIN_PROBABILITY", "0.05"))
MAX_PROBABILITY: float = float(os.getenv("MAX_PROBABILITY", "0.95"))
# Slippage tolerance (0.02 = accept up to 2 % worse price than quoted)
SLIPPAGE_TOLERANCE: float = float(os.getenv("SLIPPAGE_TOLERANCE", "0.02"))
# Cooldown seconds before copying the same market again
MARKET_COOLDOWN_SECS: int = int(os.getenv("MARKET_COOLDOWN_SECS", "300"))

# ── Rate limiting & daily caps ─────────────────────────────────────────────────
# Maximum number of trades allowed per hour (0 = unlimited)
MAX_TRADES_PER_HOUR: int = int(os.getenv("MAX_TRADES_PER_HOUR", "10"))
# Maximum USDC to spend in a single calendar day (0 = unlimited)
MAX_DAILY_LOSS_USDC: float = float(os.getenv("MAX_DAILY_LOSS_USDC", "500"))

# ── Market resolution ──────────────────────────────────────────────────────────
# Minimum fuzzy-match score to accept a market (higher = more strict)
FUZZY_MATCH_CUTOFF: float = float(os.getenv("FUZZY_MATCH_CUTOFF", "0.5"))
# Minimum market liquidity (USD) required before trading
MIN_LIQUIDITY_USDC: float = float(os.getenv("MIN_LIQUIDITY_USDC", "1000"))

# ── Reliability ────────────────────────────────────────────────────────────────
# How many times to retry a failed order placement
ORDER_RETRY_ATTEMPTS: int = int(os.getenv("ORDER_RETRY_ATTEMPTS", "3"))
# Maximum age (seconds) of a Telegram message before ignoring it as stale
MAX_MESSAGE_AGE_SECS: int = int(os.getenv("MAX_MESSAGE_AGE_SECS", "120"))

# ── Misc ───────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"
