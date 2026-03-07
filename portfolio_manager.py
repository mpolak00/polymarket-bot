"""
Portfolio / risk manager.

Decides *how much* USDC to stake on each copied whale trade, enforcing:
  - per-trade dollar cap (MAX_TRADE_SIZE_USDC)
  - per-trade wallet % cap (MAX_TRADE_PCT)
  - minimum whale size filter (MIN_WHALE_SIZE_USDC)
  - probability window filter (MIN_PROBABILITY … MAX_PROBABILITY)
  - per-market cooldown to avoid spamming the same market
  - hourly trade rate limit (MAX_TRADES_PER_HOUR)
  - daily spending cap (MAX_DAILY_LOSS_USDC)
  - minimum USDC balance check before each trade
"""
from __future__ import annotations

import time
from collections import deque
from datetime import date
from typing import Optional

import config
from logger import get_logger
from trade_parser import WhaleSignal

log = get_logger(__name__)


class PortfolioManager:
    def __init__(self) -> None:
        # market_question -> last_trade_timestamp
        self._cooldowns: dict[str, float] = {}

        # Rate limiting: sliding window of trade timestamps (last hour)
        self._trade_timestamps: deque[float] = deque()

        # Daily spend tracking
        self._daily_spend: float = 0.0
        self._spend_date: date = date.today()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _reset_daily_if_needed(self) -> None:
        today = date.today()
        if today != self._spend_date:
            log.info(
                "New day – resetting daily spend (was $%.2f)", self._daily_spend
            )
            self._daily_spend = 0.0
            self._spend_date = today

    def _purge_old_timestamps(self) -> None:
        """Remove trade timestamps older than 1 hour from the sliding window."""
        cutoff = time.time() - 3600
        while self._trade_timestamps and self._trade_timestamps[0] < cutoff:
            self._trade_timestamps.popleft()

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

    def _rate_limit_ok(self) -> bool:
        """Return True if we are below the hourly trade rate limit."""
        if config.MAX_TRADES_PER_HOUR <= 0:
            return True
        self._purge_old_timestamps()
        count = len(self._trade_timestamps)
        if count >= config.MAX_TRADES_PER_HOUR:
            log.warning(
                "Rate limit reached: %d trades in the last hour (max %d)",
                count,
                config.MAX_TRADES_PER_HOUR,
            )
            return False
        return True

    def _daily_cap_ok(self, size: float) -> bool:
        """Return True if adding `size` USDC would not exceed daily limit."""
        self._reset_daily_if_needed()
        if config.MAX_DAILY_LOSS_USDC <= 0:
            return True
        projected = self._daily_spend + size
        if projected > config.MAX_DAILY_LOSS_USDC:
            log.warning(
                "Daily spend cap: would reach $%.2f / $%.2f – skipping.",
                projected,
                config.MAX_DAILY_LOSS_USDC,
            )
            return False
        return True

    def _balance_sufficient(self, size: float, wallet_balance_usdc: float) -> bool:
        """Return True if the wallet has enough USDC for this trade."""
        if wallet_balance_usdc < size:
            log.warning(
                "Insufficient balance: need $%.2f, have $%.2f – skipping.",
                size,
                wallet_balance_usdc,
            )
            return False
        return True

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
        if not self._rate_limit_ok():
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

        # Daily spend cap
        if not self._daily_cap_ok(size):
            return None

        # Balance check (must have funds in wallet)
        if not self._balance_sufficient(size, wallet_balance_usdc):
            return None

        log.info(
            "Position size: $%.2f (raw=%.2f, pct_cap=%.2f, max=%.2f, daily_spent=%.2f/%.2f)",
            size,
            raw_size,
            pct_cap,
            config.MAX_TRADE_SIZE_USDC,
            self._daily_spend,
            config.MAX_DAILY_LOSS_USDC,
        )
        return round(size, 2)

    # ── Post-trade bookkeeping ─────────────────────────────────────────────────

    def record_trade(self, signal: WhaleSignal, size_usdc: float = 0.0) -> None:
        key = signal.market_question.lower()
        self._cooldowns[key] = time.time()

        # Update rate-limit window
        self._trade_timestamps.append(time.time())

        # Update daily spend
        self._reset_daily_if_needed()
        self._daily_spend += size_usdc

        log.info(
            "Trade recorded: cooldown set, daily spend now $%.2f / $%.2f, "
            "trades this hour: %d",
            self._daily_spend,
            config.MAX_DAILY_LOSS_USDC,
            len(self._trade_timestamps),
        )
