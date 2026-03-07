"""
Runs the async bot inside a regular thread so Flask can manage it.
"""
from __future__ import annotations

import asyncio
import os
import threading
from typing import Optional

import state
from logger import get_logger
from market_resolver import resolve_market
from polymarket_trader import PolymarketTrader
from portfolio_manager import PortfolioManager
from telegram_monitor import TelegramMonitor
from trade_parser import WhaleSignal

log = get_logger("bot_runner")


class _WebLogger:
    """Intercepts log records and pushes them to state.log_lines."""

    def emit(self, level: str, msg: str) -> None:
        state.add_log(level, msg)


_wl = _WebLogger()


class BotRunner:
    def __init__(self) -> None:
        self._trader = PolymarketTrader()
        self._pm = PortfolioManager()
        self._monitor: Optional[TelegramMonitor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def _handle_signal(self, sig: WhaleSignal) -> None:
        msg = f"Whale: {sig.outcome} ${sig.amount_usdc:,.0f}  p={sig.probability:.0%}  {sig.market_question[:60]}"
        state.add_log("INFO", msg)
        log.info(msg)

        balance = await self._trader.get_usdc_balance()
        state.add_log("INFO", f"Wallet balance: ${balance:.2f} USDC")

        size = self._pm.calculate_position_size(sig, balance)
        if size is None:
            state.add_log("WARNING", "Trade skipped by risk manager.")
            return

        resolved = await resolve_market(sig)
        if not resolved:
            state.add_log("WARNING", "Could not resolve market on Polymarket – skipping.")
            return

        dry = bool(os.getenv("DRY_RUN", "false").lower() == "true")
        success = await self._trader.place_market_order(sig, size)
        if success:
            self._pm.record_trade(sig)
            state.add_trade(
                market=sig.market_question,
                outcome=sig.outcome,
                size_usdc=size,
                probability=sig.probability,
                dry_run=dry,
                whale_addr=sig.trader_address,
            )
            state.add_log("INFO", f"Order OK: {sig.outcome} ${size:.2f}  {'[DRY]' if dry else '[LIVE]'}")

    async def _run_async(self) -> None:
        state.add_log("INFO", "Connecting to Polymarket CLOB…")
        await self._trader.connect()
        state.add_log("INFO", "CLOB connected. Starting Telegram monitor…")

        self._monitor = TelegramMonitor(on_signal=self._handle_signal)
        await self._monitor.start()

    def start(self) -> None:
        state.stop_event.clear()
        state.bot_running = True
        state.add_log("INFO", "Bot started.")

        def _thread() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_async())
            except Exception as exc:
                state.add_log("ERROR", f"Bot crashed: {exc}")
            finally:
                state.bot_running = False
                state.add_log("INFO", "Bot stopped.")

        t = threading.Thread(target=_thread, daemon=True)
        t.start()
        state.bot_thread = t

    def stop(self) -> None:
        state.stop_event.set()
        if self._loop and self._monitor:
            asyncio.run_coroutine_threadsafe(self._monitor.stop(), self._loop)
        state.bot_running = False
        state.add_log("INFO", "Stop signal sent.")


# Global singleton
runner = BotRunner()
