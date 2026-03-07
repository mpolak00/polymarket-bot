"""
Telegram monitor – listens to @PredictionRadarBot and fires a callback
for every message that parses as a whale-trade signal.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Awaitable

from telethon import TelegramClient, events
from telethon.tl.types import Message

import config
from logger import get_logger
from trade_parser import WhaleSignal, parse_whale_message

log = get_logger(__name__)

SignalCallback = Callable[[WhaleSignal], Awaitable[None]]


class TelegramMonitor:
    def __init__(self, on_signal: SignalCallback) -> None:
        self._on_signal = on_signal
        self._client = TelegramClient(
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        )

    async def start(self) -> None:
        await self._client.start(phone=config.TELEGRAM_PHONE)
        log.info("Telegram client authenticated.")

        # Resolve the whale-bot entity once (works for bots and channels)
        entity = await self._client.get_entity(config.WHALE_BOT_USERNAME)
        log.info("Monitoring entity: %s (id=%s)", config.WHALE_BOT_USERNAME, entity.id)

        @self._client.on(events.NewMessage(chats=entity))
        async def _handler(event: events.NewMessage.Event) -> None:
            msg: Message = event.message
            text = msg.message or ""
            if not text:
                return

            log.debug("Raw message: %s", text[:200])
            signal = parse_whale_message(text)
            if signal is not None:
                try:
                    await self._on_signal(signal)
                except Exception as exc:
                    log.error("Signal handler raised: %s", exc)

        log.info("Listening for whale alerts from @%s …", config.WHALE_BOT_USERNAME)
        await self._client.run_until_disconnected()

    async def stop(self) -> None:
        await self._client.disconnect()
        log.info("Telegram client disconnected.")
