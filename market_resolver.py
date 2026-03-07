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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                GAMMA_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status != 200:
                    log.error("Gamma API returned %s", resp.status)
                    return False
                data = await resp.json()
    except Exception as exc:
        log.error("Gamma API request failed: %s", exc)
        return False

    markets = data if isinstance(data, list) else data.get("markets", [])
    if not markets:
        log.warning("No markets found for: %s", signal.market_question[:80])
        return False

    # Pick the market whose question best matches
    questions = [m.get("question", "") for m in markets]
    matches = difflib.get_close_matches(
        signal.market_question, questions, n=1, cutoff=0.3
    )
    if matches:
        idx = questions.index(matches[0])
        best = markets[idx]
    else:
        best = markets[0]  # fall back to first result

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
        "Resolved market → conditionId=%s  tokenId=%s",
        signal.condition_id,
        signal.token_id,
    )
    return True
