"""
Parse whale-trade alerts sent by @PredictionRadarBot.

The bot sends messages in various formats.  This module tries several
regex patterns and returns a normalised WhaleSignal dataclass or None
if the message doesn't look like a trade alert.

Example messages observed from @PredictionRadarBot:
─────────────────────────────────────────────────────
🐋 Whale Alert!
Market: Will Donald Trump win the 2024 election?
Position: YES
Amount: $125,000
Probability: 62%
Trader: 0xABCD…1234
─────────────────────────────────────────────────────
🐋 Large Trade Detected
$88,500 on YES @ 71% — Will the Fed cut rates in Dec?
Wallet: 0x9f3a…cafe
─────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class WhaleSignal:
    market_question: str
    outcome: str            # "YES" | "NO"
    amount_usdc: float
    probability: float      # 0-1
    trader_address: Optional[str] = None
    condition_id: Optional[str] = None   # filled later by MarketResolver
    token_id: Optional[str] = None       # filled later by MarketResolver
    raw_text: str = field(default="", repr=False)

    @property
    def is_yes(self) -> bool:
        return self.outcome.upper() == "YES"


# ── Regex helpers ─────────────────────────────────────────────────────────────

_AMOUNT_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*[Kk]?",
)
_PROB_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_WALLET_RE = re.compile(r"0x[0-9a-fA-F]{4,}\b(?:…[0-9a-fA-F]{4})?")
_OUTCOME_RE = re.compile(r"\b(YES|NO)\b", re.IGNORECASE)


def _parse_amount(text: str) -> Optional[float]:
    """Extract the largest dollar amount found in text."""
    best = None
    for raw in _AMOUNT_RE.findall(text):
        val = float(raw.replace(",", ""))
        # handle shorthand like $125K
        idx = text.find(raw)
        after = text[idx + len(raw) : idx + len(raw) + 2].strip().upper()
        if after.startswith("K"):
            val *= 1_000
        elif after.startswith("M"):
            val *= 1_000_000
        if best is None or val > best:
            best = val
    return best


def _parse_probability(text: str) -> Optional[float]:
    matches = _PROB_RE.findall(text)
    if not matches:
        return None
    return float(matches[0]) / 100.0


def _parse_outcome(text: str) -> Optional[str]:
    m = _OUTCOME_RE.search(text)
    return m.group(1).upper() if m else None


def _parse_wallet(text: str) -> Optional[str]:
    m = _WALLET_RE.search(text)
    return m.group(0) if m else None


def _extract_market_question(text: str) -> Optional[str]:
    """Try several labeling patterns to extract the market question."""
    patterns = [
        r"[Mm]arket\s*[:–-]\s*(.+)",
        r"[Qq]uestion\s*[:–-]\s*(.+)",
        r"(?:on\s+(?:YES|NO)\s+@\s+\d+%\s+[—–-]+\s*)(.+)",
        r"(?:on\s+(?:YES|NO)\s+[—–-]+\s*)(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            q = m.group(1).strip().rstrip(".")
            if len(q) > 10:
                return q
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def parse_whale_message(text: str) -> Optional[WhaleSignal]:
    """
    Return a WhaleSignal if the message looks like a whale-trade alert,
    otherwise return None.
    """
    text = text.strip()

    # Quick pre-filter: must mention a dollar amount and YES/NO
    if not _AMOUNT_RE.search(text):
        return None
    if not _OUTCOME_RE.search(text):
        return None

    amount = _parse_amount(text)
    if amount is None or amount <= 0:
        log.debug("Could not parse amount from: %s", text[:80])
        return None

    outcome = _parse_outcome(text)
    if outcome is None:
        log.debug("Could not determine outcome (YES/NO) from: %s", text[:80])
        return None

    probability = _parse_probability(text)
    if probability is None:
        # Some messages omit the probability; default to 0.5 so we can still trade
        log.warning("No probability found, defaulting to 0.50")
        probability = 0.50

    market_question = _extract_market_question(text)
    if market_question is None:
        # Last resort: use the full message trimmed to 120 chars
        market_question = text[:120].replace("\n", " ")

    wallet = _parse_wallet(text)

    signal = WhaleSignal(
        market_question=market_question,
        outcome=outcome,
        amount_usdc=amount,
        probability=probability,
        trader_address=wallet,
        raw_text=text,
    )
    log.info(
        "Parsed signal: %s | %s | $%.0f | p=%.2f",
        signal.outcome,
        signal.market_question[:60],
        signal.amount_usdc,
        signal.probability,
    )
    return signal
