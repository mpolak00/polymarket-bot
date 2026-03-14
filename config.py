"""
Configuration loader – reads all settings from environment variables / .env file.

Provides clear error messages when required variables are missing instead of
crashing with a raw KeyError.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require(name: str) -> str:
    """Return env var value or exit with a clear error message."""
    val = os.environ.get(name)
    if not val:
        print(
            f"\n  ERROR: Required environment variable '{name}' is not set.\n"
            f"  Copy .env.example to .env and fill in your credentials:\n"
            f"    cp .env.example .env\n",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return val


def _require_int(name: str) -> int:
    val = _require(name)
    try:
        return int(val)
    except ValueError:
        print(f"\n  ERROR: '{name}' must be an integer, got: '{val}'\n", file=sys.stderr)
        raise SystemExit(1)


# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_API_ID: int = _require_int("TELEGRAM_API_ID")
TELEGRAM_API_HASH: str = _require("TELEGRAM_API_HASH")
TELEGRAM_PHONE: str = _require("TELEGRAM_PHONE")          # e.g. +38160...
WHALE_BOT_USERNAME: str = os.getenv("WHALE_BOT_USERNAME", "PredictionRadarBot")
# Session file path — set TELEGRAM_SESSION_DIR for Docker volume persistence
_SESSION_DIR: str = os.getenv("TELEGRAM_SESSION_DIR", "")
_SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "polymarket_watcher")
TELEGRAM_SESSION_NAME: str = os.path.join(_SESSION_DIR, _SESSION_NAME) if _SESSION_DIR else _SESSION_NAME

# ── Polymarket / Polygon ───────────────────────────────────────────────────────
POLYGON_PRIVATE_KEY: str = _require("POLYGON_PRIVATE_KEY")   # 0x-prefixed
CLOB_API_URL: str = os.getenv("CLOB_API_URL", "https://clob.polymarket.com")
GAMMA_API_URL: str = os.getenv("GAMMA_API_URL", "https://gamma-api.polymarket.com")

# ── Trading parameters ─────────────────────────────────────────────────────────
# Maximum USDC to allocate per single copied trade
MAX_TRADE_SIZE_USDC: float = float(os.getenv("MAX_TRADE_SIZE_USDC", "5"))
# Max percentage of total wallet balance to use per trade (safety cap)
MAX_TRADE_PCT: float = float(os.getenv("MAX_TRADE_PCT", "0.03"))   # 3 %
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
MAX_DAILY_LOSS_USDC: float = float(os.getenv("MAX_DAILY_LOSS_USDC", "15"))

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

# ── BTC Up/Down arbitrage ─────────────────────────────────────────────────────
# Enable the BTC arb scanner (runs alongside whale tracker)
BTC_ARB_ENABLED: bool = os.getenv("BTC_ARB_ENABLED", "false").lower() == "true"
# USDC to spend per arb trade
BTC_ARB_TRADE_SIZE_USDC: float = float(os.getenv("BTC_ARB_TRADE_SIZE_USDC", "2"))
# Minimum % price deviation from baseline to consider it a clear winner
# e.g. 1.5 means BTC must be 1.5% above/below baseline before we bet
BTC_ARB_MIN_EDGE_PCT: float = float(os.getenv("BTC_ARB_MIN_EDGE_PCT", "1.5"))
# Only enter markets closing within this many seconds
BTC_ARB_ENTRY_WINDOW_SECS: int = int(os.getenv("BTC_ARB_ENTRY_WINDOW_SECS", "300"))
# Don't buy if the winning token is already priced above this (too late, no value)
BTC_ARB_MAX_ENTRY_PRICE: float = float(os.getenv("BTC_ARB_MAX_ENTRY_PRICE", "0.80"))
# How often to scan for new opportunities (seconds)
BTC_ARB_SCAN_INTERVAL_SECS: int = int(os.getenv("BTC_ARB_SCAN_INTERVAL_SECS", "30"))

# ── Misc ───────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
