"""
Shared in-memory state between the Flask web app and the bot thread.
Thread-safe via simple list/dict + a lock.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

_lock = threading.Lock()

# ── Bot runtime state ─────────────────────────────────────────────────────────
bot_running = False
bot_thread: Optional[threading.Thread] = None
stop_event = threading.Event()

# ── Live log ring-buffer (last 200 lines) ─────────────────────────────────────
log_lines: list[dict] = []   # {"ts": "...", "level": "INFO", "msg": "..."}
MAX_LOG_LINES = 200

# ── Trade history ──────────────────────────────────────────────────────────────
trades: list[dict] = []
TRADES_FILE = os.path.join(os.path.dirname(__file__), "trades.json")

# ── Whale stats ────────────────────────────────────────────────────────────────
whale_stats: dict[str, dict] = {}  # address -> {"count": int, "total_usdc": float, "last_seen": str}


def load_trades() -> None:
    global trades
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE) as f:
                trades = json.load(f)
        except Exception:
            trades = []


def save_trades() -> None:
    with _lock:
        with open(TRADES_FILE, "w") as f:
            json.dump(trades[-500:], f, indent=2)


def add_log(level: str, msg: str) -> None:
    with _lock:
        log_lines.append({
            "ts": datetime.utcnow().strftime("%H:%M:%S"),
            "level": level,
            "msg": msg,
        })
        if len(log_lines) > MAX_LOG_LINES:
            log_lines.pop(0)


def add_trade(market: str, outcome: str, size_usdc: float,
              probability: float, dry_run: bool, whale_addr: Optional[str] = None) -> None:
    with _lock:
        trades.append({
            "ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "market": market[:80],
            "outcome": outcome,
            "size_usdc": size_usdc,
            "probability": probability,
            "dry_run": dry_run,
            "whale": whale_addr or "unknown",
        })
    save_trades()
    if whale_addr and whale_addr != "unknown":
        _update_whale(whale_addr, size_usdc)


def _update_whale(address: str, amount: float) -> None:
    with _lock:
        if address not in whale_stats:
            whale_stats[address] = {"count": 0, "total_usdc": 0.0, "last_seen": ""}
        whale_stats[address]["count"] += 1
        whale_stats[address]["total_usdc"] += amount
        whale_stats[address]["last_seen"] = datetime.utcnow().strftime("%H:%M:%S")
