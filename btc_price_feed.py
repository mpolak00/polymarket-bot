"""
Real-time BTC/USDT price feed using Binance public REST API.
No API key required.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp

from logger import get_logger

log = get_logger(__name__)

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"

# Fallback in case Binance is unreachable
_FALLBACK_URLS = [
    "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
    "https://api.coinbase.com/v2/prices/BTC-USD/spot",
]


class BtcPriceFeed:
    """
    Fetches and caches the current BTC/USD price.
    Price is re-fetched at most once every `cache_ttl_secs` seconds.
    """

    def __init__(self, cache_ttl_secs: float = 5.0) -> None:
        self._cache_ttl = cache_ttl_secs
        self._price: Optional[float] = None
        self._fetched_at: float = 0.0

    async def get_price(self) -> Optional[float]:
        """Return current BTC/USD price, using cache if fresh enough."""
        now = time.monotonic()
        if self._price is not None and (now - self._fetched_at) < self._cache_ttl:
            return self._price

        price = await self._fetch()
        if price is not None:
            self._price = price
            self._fetched_at = now
            log.debug("BTC price: $%.2f", price)
        else:
            log.warning("Could not refresh BTC price – using last known: %s", self._price)

        return self._price

    async def _fetch(self) -> Optional[float]:
        """Try Binance first, then Coinbase as fallback."""
        # ── Binance ──────────────────────────────────────────────────────────
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.binance.com/api/v3/ticker/price",
                    params={"symbol": "BTCUSDT"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data["price"])
        except Exception as exc:
            log.debug("Binance price fetch failed: %s – trying Coinbase", exc)

        # ── Coinbase fallback ─────────────────────────────────────────────────
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.coinbase.com/v2/prices/BTC-USD/spot",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data["data"]["amount"])
        except Exception as exc:
            log.warning("Coinbase price fetch also failed: %s", exc)

        return None
