"""
Polymarket Whale Tracker Bot
────────────────────────────
Monitors @PredictionRadarBot on Telegram for large trades (whales),
resolves the market on Polymarket, sizes the position according to
risk parameters, and places the order automatically.

Usage:
    python main.py

Set all required variables in .env (see .env.example) before running.
"""
from __future__ import annotations

import asyncio
import signal
import sys

import config
from logger import get_logger
from market_resolver import resolve_market
from portfolio_manager import PortfolioManager
from polymarket_trader import PolymarketTrader
from telegram_monitor import TelegramMonitor
from trade_parser import WhaleSignal

log = get_logger("main")


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
            self._pm.record_trade(signal)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def run(self) -> None:
        log.info("Connecting to Polymarket CLOB…")
        await self._trader.connect()

        if config.DRY_RUN:
            log.warning("*** DRY-RUN MODE – no real orders will be placed ***")

        log.info("Starting Telegram monitor…")
        await self._monitor.start()

    async def shutdown(self) -> None:
        await self._monitor.stop()
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

    try:
        await bot.run()
    except KeyboardInterrupt:
        await bot.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
