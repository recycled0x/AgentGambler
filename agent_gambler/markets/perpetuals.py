"""
Perpetual Futures Trading Module.

Trade perpetual futures on Hyperliquid and other perp DEXes.
Leverage, funding rates, liquidation risks - what could go wrong?

Focus areas:
- Hyperliquid integration (main perp DEX)
- ETH, SOL, and other asset perps
- Funding rate arbitrage opportunities
- Leverage management (2-5x default)
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from agent_gambler.strategies.gamblers_logic import BetType, Opportunity


@dataclass
class PerpMarket:
    symbol: str
    price: float
    funding_rate: float  # 8h funding rate
    open_interest: float
    volume_24h: float
    mark_price: float
    index_price: float
    max_leverage: float = 20.0


class PerpetualsClient:
    """
    Client for trading perpetual futures on Hyperliquid.

    Strategy: Find funding rate opportunities, ride trends with leverage,
    but don't get liquidated (that's the hard part).
    """

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._markets_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 30  # Refresh every 30 seconds

    def fetch_hyperliquid_markets(self) -> list[PerpMarket]:
        """
        Fetch perpetual markets from Hyperliquid.

        Returns list of available perp markets with funding rates.
        """
        try:
            # Hyperliquid API endpoint for market info
            response = self.session.post(
                f"{self.config.perpetuals.hyperliquid_api_url}/info",
                json={"type": "meta"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            markets = []
            if isinstance(data, dict) and "universe" in data:
                # Fetch funding rates
                funding_response = self.session.post(
                    f"{self.config.perpetuals.hyperliquid_api_url}/info",
                    json={"type": "fundingHistory"},
                    timeout=15,
                )
                funding_data = funding_response.json() if funding_response.status_code == 200 else {}

                for market_info in data.get("universe", []):
                    symbol = market_info.get("name", "")
                    if not symbol:
                        continue

                    # Get current price and funding rate
                    price_response = self.session.post(
                        f"{self.config.perpetuals.hyperliquid_api_url}/info",
                        json={"type": "allMids"},
                        timeout=15,
                    )
                    price_data = price_response.json() if price_response.status_code == 200 else {}

                    price = float(price_data.get(symbol, 0)) if isinstance(price_data, dict) else 0.0

                    # Get funding rate (simplified - would parse actual funding history)
                    funding_rate = 0.0
                    if isinstance(funding_data, dict) and symbol in funding_data:
                        # Parse funding rate from history
                        funding_rate = float(funding_data.get(symbol, [{}])[0].get("funding", 0)) if funding_data.get(symbol) else 0.0

                    markets.append(PerpMarket(
                        symbol=symbol,
                        price=price,
                        funding_rate=funding_rate,
                        open_interest=float(market_info.get("openInterest", 0)),
                        volume_24h=float(market_info.get("volume24h", 0)),
                        mark_price=price,
                        index_price=price,
                        max_leverage=float(market_info.get("maxLeverage", 20.0)),
                    ))

            return markets

        except requests.RequestException as e:
            print(f"[Perpetuals] Error fetching Hyperliquid markets: {e}")
            return []

    def analyze_perp_market(self, market: PerpMarket) -> Optional[Opportunity]:
        """
        Analyze a perpetual market for trading opportunities.

        Signals:
        1. High positive funding rate = short opportunity (get paid to short)
        2. High negative funding rate = long opportunity (get paid to long)
        3. Strong momentum + reasonable funding = trend following
        4. Mean reversion after extreme moves
        """
        if market.price <= 0:
            return None

        bet_type = None
        fair_value = market.price
        confidence = 0.5
        momentum = 0.0

        funding_rate = market.funding_rate
        funding_threshold = self.config.perpetuals.funding_rate_threshold

        # FUNDING RATE ARBITRAGE: High funding = bet against it
        if funding_rate > funding_threshold:
            # High positive funding = longs paying shorts
            # Short opportunity (get paid to short)
            bet_type = BetType.HYPERLIQUID_SHORT
            fair_value = market.price * 0.98  # Expect slight downward pressure
            confidence = min(0.60 + abs(funding_rate) * 100, 0.75)
            momentum = -0.2

        elif funding_rate < -funding_threshold:
            # High negative funding = shorts paying longs
            # Long opportunity (get paid to long)
            bet_type = BetType.HYPERLIQUID_LONG
            fair_value = market.price * 1.02  # Expect slight upward pressure
            confidence = min(0.60 + abs(funding_rate) * 100, 0.75)
            momentum = 0.2

        # MOMENTUM PLAY: High volume + price movement
        elif market.volume_24h > 10000000:  # $10M+ volume
            # Check if we can infer direction from funding (simplified)
            if funding_rate < 0:
                bet_type = BetType.HYPERLIQUID_LONG
                fair_value = market.price * 1.10
                confidence = 0.55
                momentum = 0.3
            else:
                bet_type = BetType.HYPERLIQUID_SHORT
                fair_value = market.price * 0.90
                confidence = 0.55
                momentum = -0.3

        else:
            return None  # No clear signal

        edge = abs(fair_value - market.price) / market.price
        if edge < 0.03:  # Less than 3% expected move, not worth it
            return None

        # Calculate time sensitivity (funding rates reset every 8h)
        time_sensitivity = 0.5 if abs(funding_rate) > funding_threshold else 0.2

        return Opportunity(
            market_id=market.symbol,
            market_name=f"[Perp] {market.symbol}",
            bet_type=bet_type,
            current_price=market.price,
            estimated_fair_value=fair_value,
            confidence=confidence,
            volume_24h=market.volume_24h,
            momentum_score=momentum,
            time_sensitivity=time_sensitivity,
            meta={
                "platform": "hyperliquid",
                "symbol": market.symbol,
                "funding_rate": funding_rate,
                "open_interest": market.open_interest,
                "max_leverage": market.max_leverage,
                "mark_price": market.mark_price,
                "index_price": market.index_price,
            },
        )

    def scan_for_opportunities(self) -> list[Opportunity]:
        """
        Main scanning function for perpetual futures opportunities.

        Finds funding rate plays, momentum trades, and mean reversion setups.
        """
        markets = self.fetch_hyperliquid_markets()
        opportunities = []

        # Focus on major markets: ETH, SOL, BTC
        major_symbols = ["ETH", "SOL", "BTC"]
        major_markets = [m for m in markets if m.symbol in major_symbols]

        for market in major_markets:
            opp = self.analyze_perp_market(market)
            if opp:
                opportunities.append(opp)

        # Sort by perceived edge
        opportunities.sort(key=lambda o: o.perceived_edge, reverse=True)

        return opportunities

    def calculate_liquidation_price(self, entry_price: float, side: str, 
                                     leverage: float, collateral: float) -> float:
        """
        Calculate liquidation price for a perp position.

        Simplified calculation - actual liquidation depends on exchange rules.
        """
        if side == "long":
            # Long liquidation: price drops too much
            # Liq price = entry * (1 - (1 - liquidation_buffer) / leverage)
            buffer = self.config.perpetuals.liquidation_buffer
            liq_price = entry_price * (1 - (1 - buffer) / leverage)
        else:
            # Short liquidation: price rises too much
            buffer = self.config.perpetuals.liquidation_buffer
            liq_price = entry_price * (1 + (1 - buffer) / leverage)

        return liq_price
