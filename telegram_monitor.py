"""
Telegram monitor – listens to @PredictionRadarBot and fires a callback
for every message that parses as a whale-trade signal.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import timezone
from typing import Callable, Awaitable

from telethon import TelegramClient, events
from telethon.tl.types import Message

import config
from logger import get_logger
from trade_parser import WhaleSignal, parse_whale_message

log = get_logger(__name__)

SignalCallback = Callable[[WhaleSignal], Awaitable[None]]

# Max number of recent message IDs to remember for dedup
_DEDUP_CACHE_SIZE = 500


class TelegramMonitor:
    def __init__(self, on_signal: SignalCallback) -> None:
        self._on_signal = on_signal
        self._client = TelegramClient(
            config.TELEGRAM_SESSION_NAME,
            config.TELEGRAM_API_ID,
            config.TELEGRAM_API_HASH,
        )
        # Sliding window of recently seen message IDs for deduplication
        self._seen_ids: deque[int] = deque(maxlen=_DEDUP_CACHE_SIZE)

    def _is_duplicate(self, msg_id: int) -> bool:
        if msg_id in self._seen_ids:
            log.debug("Duplicate message id=%d – ignoring.", msg_id)
            return True
        self._seen_ids.append(msg_id)
        return False

    def _is_stale(self, msg: Message) -> bool:
        """Return True if the message is older than MAX_MESSAGE_AGE_SECS."""
        if config.MAX_MESSAGE_AGE_SECS <= 0:
            return False
        if msg.date is None:
            return False
        msg_ts = msg.date.replace(tzinfo=timezone.utc).timestamp()
        age = time.time() - msg_ts
        if age > config.MAX_MESSAGE_AGE_SECS:
            log.info(
                "Stale message id=%d (age=%.0fs > %ds) – ignoring.",
                msg.id, age, config.MAX_MESSAGE_AGE_SECS,
            )
            return True
        return False

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

            # Skip duplicate messages (e.g. edits delivered twice)
            if self._is_duplicate(msg.id):
                return

            # Skip messages that arrived too late (stale signals)
            if self._is_stale(msg):
                return

            log.debug("Raw message id=%d: %s", msg.id, text[:200])
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
