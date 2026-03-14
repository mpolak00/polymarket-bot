"""
BTC Up/Down arbitrage scanner.

Strategy (same as gabagool22):
  1. Every BTC_ARB_SCAN_INTERVAL_SECS scan Polymarket for "Bitcoin Up or Down"
     markets that close within BTC_ARB_ENTRY_WINDOW_SECS seconds.
  2. Parse the baseline BTC price from the market description.
  3. Fetch live BTC price from Binance/Coinbase.
  4. If the price is already BTC_ARB_MIN_EDGE_PCT% away from the baseline
     (and the market is still offering a cheap price), buy the winning side.

Example:
  Market: "Will Bitcoin be above $95,230 at 10:00PM ET?" closing in 3 min.
  Live BTC:  $96,100  →  +0.91% above baseline  →  "Up" is very likely.
  If "Up" token is still priced at 15¢ → great edge → buy.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import aiohttp

import config
from btc_price_feed import BtcPriceFeed
from logger import get_logger
from polymarket_trader import PolymarketTrader

log = get_logger(__name__)

GAMMA_MARKETS_URL = f"{config.GAMMA_API_URL}/markets"

# Regex patterns to extract baseline price from market descriptions
# e.g. "Will Bitcoin be above $95,230.50 at..."
# e.g. "BTC price above 95230 at..."
_PRICE_RE = re.compile(
    r"\$?([\d,]+(?:\.\d+)?)\s*(?:USD|USDT)?",
    re.IGNORECASE,
)

# Market question pattern
_QUESTION_RE = re.compile(
    r"bitcoin.{0,20}(up|down|above|below|higher|lower)",
    re.IGNORECASE,
)


class BtcArbScanner:
    """
    Continuously scans for profitable BTC Up/Down arbitrage opportunities.
    Runs independently of the whale-tracking pipeline.
    """

    def __init__(self, trader: PolymarketTrader) -> None:
        self._trader = trader
        self._price_feed = BtcPriceFeed(cache_ttl_secs=3.0)
        # Track markets we already bet on in this session (condition_id)
        self._traded: set[str] = set()

    # ── Main loop ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        log.info(
            "BTC arb scanner started  (scan_interval=%ds  entry_window=%ds  "
            "min_edge=%.1f%%  trade_size=$%.0f)",
            config.BTC_ARB_SCAN_INTERVAL_SECS,
            config.BTC_ARB_ENTRY_WINDOW_SECS,
            config.BTC_ARB_MIN_EDGE_PCT,
            config.BTC_ARB_TRADE_SIZE_USDC,
        )
        while True:
            try:
                await self._scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("BTC arb scan error: %s", exc)
            await asyncio.sleep(config.BTC_ARB_SCAN_INTERVAL_SECS)

    # ── Single scan ───────────────────────────────────────────────────────────

    async def _scan_once(self) -> None:
        markets = await self._fetch_btc_markets()
        if not markets:
            return

        btc_price = await self._price_feed.get_price()
        if btc_price is None:
            log.warning("BTC arb: no price available, skipping scan.")
            return

        log.debug("BTC arb scan: %d markets, BTC=$%.2f", len(markets), btc_price)

        for market in markets:
            await self._evaluate(market, btc_price)

    # ── Market fetching ───────────────────────────────────────────────────────

    async def _fetch_btc_markets(self) -> list[dict]:
        """Return active BTC Up/Down markets closing within the entry window."""
        params = {
            "q": "Bitcoin Up or Down",
            "active": "true",
            "closed": "false",
            "limit": 20,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    GAMMA_MARKETS_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
        except Exception as exc:
            log.warning("BTC arb: Gamma API error: %s", exc)
            return []

        raw = data if isinstance(data, list) else data.get("markets", [])
        now = datetime.now(timezone.utc).timestamp()
        result = []

        for m in raw:
            # Only consider markets closing soon
            end_ts = self._parse_end_ts(m)
            if end_ts is None:
                continue
            secs_to_close = end_ts - now
            if secs_to_close <= 0 or secs_to_close > config.BTC_ARB_ENTRY_WINDOW_SECS:
                continue
            result.append({**m, "_secs_to_close": secs_to_close})

        return result

    @staticmethod
    def _parse_end_ts(market: dict) -> Optional[float]:
        """Extract close timestamp from market dict."""
        for key in ("endDate", "end_date", "endDateIso", "closeTime"):
            val = market.get(key)
            if val:
                try:
                    dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                    return dt.timestamp()
                except ValueError:
                    pass
        return None

    # ── Edge evaluation ───────────────────────────────────────────────────────

    async def _evaluate(self, market: dict, btc_price: float) -> None:
        condition_id = market.get("conditionId") or market.get("condition_id", "")
        if not condition_id or condition_id in self._traded:
            return

        question = market.get("question", "")
        description = market.get("description", "") or question

        # Extract baseline price
        baseline = self._extract_baseline(description)
        if baseline is None:
            log.debug("BTC arb: no baseline found in: %s", description[:120])
            return

        # Calculate edge
        pct_diff = (btc_price - baseline) / baseline * 100
        secs_to_close = market["_secs_to_close"]

        log.debug(
            "BTC arb: %s | baseline=$%.2f | live=$%.2f | diff=%.2f%% | closes in %.0fs",
            question[:60], baseline, btc_price, pct_diff, secs_to_close,
        )

        # Determine winning side and whether we have enough edge
        if pct_diff >= config.BTC_ARB_MIN_EDGE_PCT:
            winning_outcome = "UP"
        elif pct_diff <= -config.BTC_ARB_MIN_EDGE_PCT:
            winning_outcome = "DOWN"
        else:
            return  # Not enough edge

        log.info(
            "BTC arb OPPORTUNITY: %s | diff=%.2f%% → %s | closes in %.0fs",
            question[:60], pct_diff, winning_outcome, secs_to_close,
        )

        await self._place_arb_trade(market, winning_outcome, baseline, btc_price)

    @staticmethod
    def _extract_baseline(text: str) -> Optional[float]:
        """Find the largest dollar amount in the text – that's the baseline price."""
        matches = _PRICE_RE.findall(text)
        if not matches:
            return None
        candidates = []
        for m in matches:
            try:
                val = float(m.replace(",", ""))
                # BTC price is typically > 1000, filter out percentages / small numbers
                if val > 1000:
                    candidates.append(val)
            except ValueError:
                pass
        return max(candidates) if candidates else None

    # ── Order placement ───────────────────────────────────────────────────────

    async def _place_arb_trade(
        self,
        market: dict,
        outcome: str,
        baseline: float,
        btc_price: float,
    ) -> None:
        # Find the token for the winning outcome
        tokens = market.get("tokens") or market.get("clobTokenIds") or []
        token_id: Optional[str] = None
        token_price: float = 0.5  # default

        if isinstance(tokens, list) and tokens:
            if isinstance(tokens[0], dict):
                for tok in tokens:
                    if tok.get("outcome", "").upper() in (outcome, outcome.capitalize()):
                        token_id = tok.get("token_id") or tok.get("tokenId")
                        token_price = float(tok.get("price", 0.5) or 0.5)
                        break
            else:
                # [yes_token, no_token]
                token_id = tokens[0] if outcome == "UP" else tokens[1]

        if not token_id:
            log.warning("BTC arb: no token_id for %s outcome in market %s", outcome, market.get("conditionId"))
            return

        # Skip if the market is already pricing the winning side expensively
        if token_price > config.BTC_ARB_MAX_ENTRY_PRICE:
            log.info(
                "BTC arb: %s already priced at %.2f > max_entry=%.2f – skipping.",
                outcome, token_price, config.BTC_ARB_MAX_ENTRY_PRICE,
            )
            return

        if config.DRY_RUN:
            log.info(
                "[DRY-RUN] BTC arb: would buy $%.2f of %s @ %.2f  (baseline=$%.2f live=$%.2f)",
                config.BTC_ARB_TRADE_SIZE_USDC,
                outcome,
                token_price,
                baseline,
                btc_price,
            )
            self._traded.add(market.get("conditionId", ""))
            return

        # Build a minimal signal-like object compatible with place_market_order
        from trade_parser import WhaleSignal
        arb_signal = WhaleSignal(
            market_question=market.get("question", "BTC Up/Down"),
            outcome=outcome,
            amount_usdc=config.BTC_ARB_TRADE_SIZE_USDC,
            probability=token_price,
        )
        arb_signal.condition_id = market.get("conditionId") or market.get("condition_id")
        arb_signal.token_id = token_id

        success = await self._trader.place_market_order(
            arb_signal, config.BTC_ARB_TRADE_SIZE_USDC
        )
        if success:
            self._traded.add(market.get("conditionId", ""))
            log.info(
                "BTC arb trade executed: %s %s $%.2f  (edge=%.2f%%)",
                outcome,
                market.get("question", "")[:50],
                config.BTC_ARB_TRADE_SIZE_USDC,
                abs((btc_price - baseline) / baseline * 100),
            )
