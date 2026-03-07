"""
Portfolio / risk manager.

Decides *how much* USDC to stake on each copied whale trade, enforcing:
  - per-trade dollar cap (MAX_TRADE_SIZE_USDC)
  - per-trade wallet % cap (MAX_TRADE_PCT)
  - minimum whale size filter (MIN_WHALE_SIZE_USDC)
  - probability window filter (MIN_PROBABILITY … MAX_PROBABILITY)
  - per-market cooldown to avoid spamming the same market
"""
from __future__ import annotations

import time
from typing import Optional

import config
from logger import get_logger
from trade_parser import WhaleSignal

log = get_logger(__name__)


class PortfolioManager:
    def __init__(self) -> None:
        # market_question -> last_trade_timestamp
        self._cooldowns: dict[str, float] = {}

    # ── Filtering ──────────────────────────────────────────────────────────────

    def _is_on_cooldown(self, signal: WhaleSignal) -> bool:
        key = signal.market_question.lower()
        last = self._cooldowns.get(key, 0)
        elapsed = time.time() - last
        if elapsed < config.MARKET_COOLDOWN_SECS:
            log.info(
                "Cooldown active for '%s' (%.0fs remaining)",
                signal.market_question[:60],
                config.MARKET_COOLDOWN_SECS - elapsed,
            )
            return True
        return False

    def _probability_ok(self, signal: WhaleSignal) -> bool:
        ok = config.MIN_PROBABILITY <= signal.probability <= config.MAX_PROBABILITY
        if not ok:
            log.info(
                "Skipping – probability %.2f outside [%.2f, %.2f]",
                signal.probability,
                config.MIN_PROBABILITY,
                config.MAX_PROBABILITY,
            )
        return ok

    def _whale_size_ok(self, signal: WhaleSignal) -> bool:
        ok = signal.amount_usdc >= config.MIN_WHALE_SIZE_USDC
        if not ok:
            log.info(
                "Skipping – whale size $%.0f < minimum $%.0f",
                signal.amount_usdc,
                config.MIN_WHALE_SIZE_USDC,
            )
        return ok

    # ── Size calculation ───────────────────────────────────────────────────────

    def calculate_position_size(
        self, signal: WhaleSignal, wallet_balance_usdc: float
    ) -> Optional[float]:
        """
        Return the USDC amount to trade, or None if the trade should be skipped.
        """
        if not self._whale_size_ok(signal):
            return None
        if not self._probability_ok(signal):
            return None
        if self._is_on_cooldown(signal):
            return None

        # Scale proportionally to the whale trade
        raw_size = signal.amount_usdc * config.COPY_SCALE_FACTOR

        # Enforce caps
        pct_cap = wallet_balance_usdc * config.MAX_TRADE_PCT
        size = min(raw_size, config.MAX_TRADE_SIZE_USDC, pct_cap)

        # Minimum viable order
        if size < 1.0:
            log.info("Calculated size $%.2f too small – skipping.", size)
            return None

        log.info(
            "Position size: $%.2f (raw=%.2f, pct_cap=%.2f, max=%.2f)",
            size,
            raw_size,
            pct_cap,
            config.MAX_TRADE_SIZE_USDC,
        )
        return round(size, 2)

    # ── Post-trade bookkeeping ─────────────────────────────────────────────────

    def record_trade(self, signal: WhaleSignal) -> None:
        key = signal.market_question.lower()
        self._cooldowns[key] = time.time()
        log.info("Cooldown set for '%s'", signal.market_question[:60])
