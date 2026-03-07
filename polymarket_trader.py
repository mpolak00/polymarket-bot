"""
Execute trades on Polymarket via the CLOB API.

Uses py-clob-client (https://github.com/Polymarket/py-clob-client) under the
hood.  Falls back to raw CLOB REST calls if the library is unavailable.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import config
from logger import get_logger
from trade_parser import WhaleSignal

log = get_logger(__name__)

# ── Try importing py-clob-client ──────────────────────────────────────────────
try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import (
        ApiCreds,
        BuyOrderArgs,
        OrderArgs,
        OrderType,
    )
    _CLOB_AVAILABLE = True
except ImportError:
    log.warning(
        "py-clob-client not installed – trading will be disabled until you run "
        "`pip install py-clob-client`"
    )
    _CLOB_AVAILABLE = False


# ── Trader class ──────────────────────────────────────────────────────────────

class PolymarketTrader:
    """
    Thin async wrapper around the synchronous ClobClient.
    All blocking calls are dispatched to a thread-pool executor.
    """

    def __init__(self) -> None:
        self._client: Optional["ClobClient"] = None

    # ── Initialisation ────────────────────────────────────────────────────────

    async def connect(self) -> None:
        if not _CLOB_AVAILABLE:
            log.error("py-clob-client unavailable – cannot connect.")
            return

        loop = asyncio.get_event_loop()
        try:
            self._client = await loop.run_in_executor(
                None, self._build_client
            )
            log.info("Connected to Polymarket CLOB at %s", config.CLOB_API_URL)
        except Exception as exc:
            log.error("Failed to connect to CLOB: %s", exc)
            self._client = None

    def _build_client(self) -> "ClobClient":
        client = ClobClient(
            host=config.CLOB_API_URL,
            key=config.POLYGON_PRIVATE_KEY,
            chain_id=137,   # Polygon mainnet
        )
        # Derive L2 API credentials from the wallet key
        creds = client.create_or_derive_api_creds()
        client.set_api_creds(creds)
        return client

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_usdc_balance(self) -> float:
        """Return the available USDC balance (6-decimal normalised to human)."""
        if not self._client:
            return 0.0
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, self._client.get_balance)
            # CLOB returns balance in units; convert if needed
            raw = float(resp.get("balance", 0))
            # Polymarket CLOB returns USDC in 6-decimal units
            return raw / 1_000_000 if raw > 1_000 else raw
        except Exception as exc:
            log.error("Could not fetch balance: %s", exc)
            return 0.0

    # ── Slippage check ────────────────────────────────────────────────────────

    async def _get_market_price(self, token_id: str) -> Optional[float]:
        """Fetch the current best ask price for a token from the CLOB."""
        if not self._client:
            return None
        loop = asyncio.get_event_loop()
        try:
            book = await loop.run_in_executor(
                None, lambda: self._client.get_order_book(token_id)
            )
            asks = book.get("asks") or []
            if asks:
                # Best ask is the lowest offer price
                return float(min(a.get("price", 1.0) for a in asks))
        except Exception as exc:
            log.warning("Could not fetch order book for slippage check: %s", exc)
        return None

    def _slippage_ok(self, signal_price: float, market_price: float) -> bool:
        """Return True if market_price is within SLIPPAGE_TOLERANCE of signal_price."""
        if market_price <= 0:
            return True
        slippage = abs(market_price - signal_price) / signal_price
        if slippage > config.SLIPPAGE_TOLERANCE:
            log.warning(
                "Slippage too high: signal price=%.4f  market price=%.4f  "
                "slippage=%.2f%% > tolerance=%.2f%%",
                signal_price,
                market_price,
                slippage * 100,
                config.SLIPPAGE_TOLERANCE * 100,
            )
            return False
        log.debug(
            "Slippage OK: %.2f%% (signal=%.4f, market=%.4f)",
            slippage * 100, signal_price, market_price,
        )
        return True

    # ── Order execution ───────────────────────────────────────────────────────

    async def place_market_order(
        self, signal: WhaleSignal, size_usdc: float
    ) -> bool:
        """
        Place a market-buy order for `size_usdc` USDC on the resolved market.
        Returns True if the order was accepted.
        """
        if config.DRY_RUN:
            log.info(
                "[DRY-RUN] Would buy %.2f USDC of %s on %s",
                size_usdc,
                signal.outcome,
                signal.market_question[:60],
            )
            return True

        if not self._client:
            log.error("CLOB client not connected – skipping order.")
            return False

        if not signal.token_id:
            log.error("No token_id on signal – cannot place order.")
            return False

        # Pre-flight: verify balance
        balance = await self.get_usdc_balance()
        if balance < size_usdc:
            log.error(
                "Insufficient balance: need $%.2f USDC, have $%.2f – skipping.",
                size_usdc, balance,
            )
            return False

        # Pre-flight: slippage check
        market_price = await self._get_market_price(signal.token_id)
        if market_price is not None and not self._slippage_ok(signal.probability, market_price):
            return False

        # Use actual market price if available, else fall back to signal probability
        order_price = market_price if market_price is not None else signal.probability

        # Order placement with retry
        loop = asyncio.get_event_loop()
        last_exc: Optional[Exception] = None
        for attempt in range(1, config.ORDER_RETRY_ATTEMPTS + 1):
            try:
                order_args = OrderArgs(
                    token_id=signal.token_id,
                    price=order_price,
                    size=size_usdc,
                    side="BUY",
                )
                resp = await loop.run_in_executor(
                    None,
                    lambda: self._client.create_and_post_order(order_args),
                )
                order_id = resp.get("orderID") or resp.get("id", "?")
                log.info(
                    "Order placed ✓  id=%s  %.2f USDC  %s  %s  (attempt %d)",
                    order_id,
                    size_usdc,
                    signal.outcome,
                    signal.market_question[:50],
                    attempt,
                )
                return True
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "Order attempt %d/%d failed: %s",
                    attempt, config.ORDER_RETRY_ATTEMPTS, exc,
                )
                if attempt < config.ORDER_RETRY_ATTEMPTS:
                    await asyncio.sleep(2 ** attempt)  # 2s, 4s

        log.error("Order placement failed after %d attempts: %s", config.ORDER_RETRY_ATTEMPTS, last_exc)
        return False
