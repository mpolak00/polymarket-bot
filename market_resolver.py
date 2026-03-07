"""
Resolve a free-text market question to a Polymarket conditionId / tokenId
by querying the Gamma Markets API.
"""
from __future__ import annotations

import asyncio
import difflib
from typing import Optional

import aiohttp

import config
from logger import get_logger
from trade_parser import WhaleSignal

log = get_logger(__name__)

GAMMA_SEARCH_URL = f"{config.GAMMA_API_URL}/markets"

# ── Retry helper ──────────────────────────────────────────────────────────────

async def _get_json(url: str, params: dict) -> Optional[object]:
    """GET with exponential-backoff retry. Returns parsed JSON or None."""
    for attempt in range(1, 4):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    log.warning("Gamma API HTTP %s (attempt %s/3)", resp.status, attempt)
        except asyncio.TimeoutError:
            log.warning("Gamma API timeout (attempt %s/3)", attempt)
        except Exception as exc:
            log.warning("Gamma API error (attempt %s/3): %s", attempt, exc)

        if attempt < 3:
            await asyncio.sleep(2 ** attempt)  # 2s, 4s

    log.error("Gamma API unavailable after 3 attempts.")
    return None


# ── Liquidity check ───────────────────────────────────────────────────────────

def _has_liquidity(market: dict) -> bool:
    """Return True if the market has enough liquidity to trade."""
    if config.MIN_LIQUIDITY_USDC <= 0:
        return True
    liquidity = float(market.get("liquidityNum") or market.get("liquidity") or 0)
    if liquidity < config.MIN_LIQUIDITY_USDC:
        log.info(
            "Skipping market – liquidity $%.0f < minimum $%.0f  (%s)",
            liquidity,
            config.MIN_LIQUIDITY_USDC,
            market.get("question", "")[:60],
        )
        return False
    return True


# ── Main resolver ─────────────────────────────────────────────────────────────

async def resolve_market(signal: WhaleSignal) -> bool:
    """
    Query Gamma API for markets matching signal.market_question.
    Fills signal.condition_id and signal.token_id in place.
    Returns True on success.
    """
    params = {
        "q": signal.market_question[:120],
        "active": "true",
        "closed": "false",
        "limit": 10,
    }

    data = await _get_json(GAMMA_SEARCH_URL, params)
    if data is None:
        return False

    markets = data if isinstance(data, list) else data.get("markets", [])
    if not markets:
        log.warning("No markets found for: %s", signal.market_question[:80])
        return False

    # Pick the market whose question best matches using stricter cutoff
    questions = [m.get("question", "") for m in markets]
    matches = difflib.get_close_matches(
        signal.market_question, questions, n=1, cutoff=config.FUZZY_MATCH_CUTOFF
    )
    if not matches:
        log.warning(
            "No fuzzy match above %.2f for: %s",
            config.FUZZY_MATCH_CUTOFF,
            signal.market_question[:80],
        )
        return False

    idx = questions.index(matches[0])
    best = markets[idx]

    # Verify market has sufficient liquidity
    if not _has_liquidity(best):
        return False

    signal.condition_id = best.get("conditionId") or best.get("condition_id")

    # Find the correct token for YES or NO
    tokens = best.get("tokens") or best.get("clobTokenIds") or []
    if isinstance(tokens, list) and tokens:
        if isinstance(tokens[0], dict):
            # Format: [{"outcome": "Yes", "token_id": "..."}, ...]
            for tok in tokens:
                outcome = tok.get("outcome", "").upper()
                if outcome == signal.outcome:
                    signal.token_id = tok.get("token_id") or tok.get("tokenId")
                    break
        else:
            # Format: ["token_id_yes", "token_id_no"]
            signal.token_id = tokens[0] if signal.is_yes else tokens[1]

    if not signal.condition_id or not signal.token_id:
        log.warning(
            "Could not resolve conditionId/tokenId for: %s", signal.market_question[:80]
        )
        return False

    log.info(
        "Resolved market → conditionId=%s  tokenId=%s  liquidity=$%.0f",
        signal.condition_id,
        signal.token_id,
        float(best.get("liquidityNum") or best.get("liquidity") or 0),
    )
    return True
