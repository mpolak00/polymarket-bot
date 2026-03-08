"""
Polymarket Whale Tracker Bot
────────────────────────────
Two strategies run in parallel:

1. Whale copy-trading: monitors @PredictionRadarBot on Telegram for large
   trades and copies them proportionally into your Polymarket wallet.

2. BTC Up/Down arbitrage (optional, set BTC_ARB_ENABLED=true): scans for
   "Bitcoin Up or Down" markets closing soon and buys the winning side when
   the live BTC price clearly indicates the outcome.

Usage:
    python main.py

Set all required variables in .env (see .env.example) before running.
"""
from __future__ import annotations

import asyncio
import signal
import sys

import config
from btc_arb import BtcArbScanner
from logger import get_logger
from market_resolver import resolve_market
from portfolio_manager import PortfolioManager
from polymarket_trader import PolymarketTrader
from telegram_monitor import TelegramMonitor
from trade_parser import WhaleSignal

log = get_logger("main")


# ── Config validation ─────────────────────────────────────────────────────────

def _validate_config() -> None:
    """Warn about risky or obviously wrong config combinations on startup."""
    errors = []
    warnings = []

    if config.MAX_TRADE_PCT > 0.20:
        warnings.append(
            f"MAX_TRADE_PCT={config.MAX_TRADE_PCT:.0%} is very high – "
            "consider keeping it ≤ 20% to limit per-trade exposure."
        )
    if config.MIN_PROBABILITY < 0.02:
        warnings.append(
            f"MIN_PROBABILITY={config.MIN_PROBABILITY} is extremely low – "
            "you may copy very unlikely markets."
        )
    if config.MAX_PROBABILITY > 0.98:
        warnings.append(
            f"MAX_PROBABILITY={config.MAX_PROBABILITY} is extremely high – "
            "you may copy near-certain markets with poor upside."
        )
    if config.COPY_SCALE_FACTOR > 0.1:
        warnings.append(
            f"COPY_SCALE_FACTOR={config.COPY_SCALE_FACTOR} is large – "
            "position sizes will be substantial relative to whale trades."
        )
    if config.MARKET_COOLDOWN_SECS < 60:
        warnings.append(
            f"MARKET_COOLDOWN_SECS={config.MARKET_COOLDOWN_SECS}s is very short – "
            "you may trade the same market multiple times rapidly."
        )
    if config.MAX_DAILY_LOSS_USDC > 0 and config.MAX_DAILY_LOSS_USDC < config.MAX_TRADE_SIZE_USDC:
        errors.append(
            f"MAX_DAILY_LOSS_USDC={config.MAX_DAILY_LOSS_USDC} is less than "
            f"MAX_TRADE_SIZE_USDC={config.MAX_TRADE_SIZE_USDC} – "
            "the daily cap is smaller than a single trade; no trades will execute."
        )
    if not config.DRY_RUN and not config.POLYGON_PRIVATE_KEY.startswith("0x"):
        errors.append("POLYGON_PRIVATE_KEY must start with '0x'.")

    for w in warnings:
        log.warning("[CONFIG] %s", w)
    for e in errors:
        log.error("[CONFIG] %s", e)

    if errors:
        raise SystemExit(
            f"Configuration has {len(errors)} critical error(s) – fix before running."
        )

    log.info(
        "Config OK: DRY_RUN=%s  MAX_TRADE=$%.0f  MAX_DAILY=$%.0f  "
        "RATE_LIMIT=%d/hr  SCALE=%.4f  FUZZY_CUTOFF=%.2f",
        config.DRY_RUN,
        config.MAX_TRADE_SIZE_USDC,
        config.MAX_DAILY_LOSS_USDC,
        config.MAX_TRADES_PER_HOUR,
        config.COPY_SCALE_FACTOR,
        config.FUZZY_MATCH_CUTOFF,
    )


class WhaleTrackerBot:
    def __init__(self) -> None:
        self._trader = PolymarketTrader()
        self._pm = PortfolioManager()
        self._monitor = TelegramMonitor(on_signal=self._handle_signal)

    # ── Core pipeline ─────────────────────────────────────────────────────────

    async def _handle_signal(self, signal: WhaleSignal) -> None:
        """Full pipeline: filter → resolve → size → trade."""
        log.info(
            "=== New whale signal: %s %s  $%.0f  p=%.2f ===",
            signal.outcome,
            signal.market_question[:60],
            signal.amount_usdc,
            signal.probability,
        )

        # 1. Get current wallet balance for position sizing
        balance = await self._trader.get_usdc_balance()
        log.info("Wallet balance: $%.2f USDC", balance)

        # 2. Portfolio manager: decide size (or skip)
        size = self._pm.calculate_position_size(signal, balance)
        if size is None:
            log.info("Trade skipped by risk manager.")
            return

        # 3. Resolve the free-text question to a conditionId / tokenId
        resolved = await resolve_market(signal)
        if not resolved:
            log.warning("Could not resolve market – skipping trade.")
            return

        # 4. Execute the order
        success = await self._trader.place_market_order(signal, size)
        if success:
            self._pm.record_trade(signal, size_usdc=size)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        log.info("Connecting to Polymarket CLOB…")
        await self._trader.connect()

        if config.DRY_RUN:
            log.warning("*** DRY-RUN MODE – no real orders will be placed ***")

        tasks = []

        # Strategy 1: BTC arbitrage scanner (optional)
        if config.BTC_ARB_ENABLED:
            arb = BtcArbScanner(self._trader)
            tasks.append(asyncio.create_task(arb.run(), name="btc-arb"))
            log.info("BTC arb scanner enabled.")
        else:
            log.info("BTC arb scanner disabled (set BTC_ARB_ENABLED=true to enable).")

        # Strategy 2: Whale copy-trading via Telegram (always on)
        log.info("Starting Telegram monitor…")
        if tasks:
            # Run both concurrently; Telegram blocks until disconnected
            tasks.append(asyncio.create_task(self._monitor.start(), name="telegram"))
            await asyncio.gather(*tasks)
        else:
            await self._monitor.start()

    async def shutdown(self) -> None:
        await self._monitor.stop()
        # Cancel any background tasks
        for task in asyncio.all_tasks():
            if task.get_name() in ("btc-arb", "telegram") and not task.done():
                task.cancel()
        log.info("Bot shut down.")


# ── Entry point ───────────────────────────────────────────────────────────────

async def _main() -> None:
    bot = WhaleTrackerBot()

    loop = asyncio.get_running_loop()

    def _stop(sig: int, _frame: object) -> None:
        log.info("Received signal %s – shutting down…", signal.Signals(sig).name)
        loop.create_task(bot.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop, sig, None)
        except NotImplementedError:
            pass  # Windows

    _validate_config()

    try:
        await bot.run()
    except KeyboardInterrupt:
        await bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
