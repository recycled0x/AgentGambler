"""
Polymarket Integration Module.

Prediction markets are just gambling with extra steps.
And we LOVE extra steps.

Polymarket CLOB API integration for:
- Fetching active markets
- Analyzing market prices and volume
- Placing orders (YES/NO positions)
- Monitoring positions
"""

import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from agent_gambler.strategies.gamblers_logic import BetType, Opportunity


@dataclass
class PolymarketMarket:
    condition_id: str
    question: str
    description: str
    yes_price: float
    no_price: float
    volume_24h: float
    liquidity: float
    end_date: str
    category: str = ""
    tokens: list = field(default_factory=list)


class PolymarketClient:
    """
    Client for the Polymarket CLOB API.

    Finds markets where the crowd is wrong and we are right.
    (We are always right. This is the way.)
    """

    BASE_URL = "https://clob.polymarket.com"
    GAMMA_URL = "https://gamma-api.polymarket.com"

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._markets_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 60  # Refresh every 60 seconds

    def fetch_active_markets(self, limit: int = 50) -> list[PolymarketMarket]:
        """
        Fetch active prediction markets from Polymarket.

        We want:
        - High volume (liquidity = ability to enter/exit)
        - Mispriced markets (where our galaxy brain sees what others don't)
        - Markets expiring soon (time pressure = opportunity)
        """
        try:
            # Use Gamma API for market discovery
            response = self.session.get(
                f"{self.GAMMA_URL}/markets",
                params={
                    "limit": limit,
                    "active": True,
                    "closed": False,
                    "order": "volume24hr",
                    "ascending": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()

            markets = []
            for m in data:
                try:
                    yes_price = float(m.get("outcomePrices", "[0.5,0.5]").strip("[]").split(",")[0])
                    no_price = 1 - yes_price
                    market = PolymarketMarket(
                        condition_id=m.get("conditionId", ""),
                        question=m.get("question", ""),
                        description=m.get("description", ""),
                        yes_price=yes_price,
                        no_price=no_price,
                        volume_24h=float(m.get("volume24hr", 0)),
                        liquidity=float(m.get("liquidity", 0)),
                        end_date=m.get("endDate", ""),
                        category=m.get("category", ""),
                    )
                    markets.append(market)
                except (ValueError, IndexError, KeyError):
                    continue

            return markets

        except requests.RequestException as e:
            print(f"[Polymarket] Error fetching markets: {e}")
            return []

    def analyze_market(self, market: PolymarketMarket) -> Optional[Opportunity]:
        """
        Analyze a single market for betting opportunities.

        Our edge detection:
        1. Price near extremes (< 0.10 or > 0.90) = potential value
        2. High volume + price movement = momentum play
        3. Mispricing detection based on our (delusional) model
        """
        # Skip low-liquidity markets (can't exit if wrong... not that we'd be wrong)
        if market.liquidity < 1000:
            return None

        # Analyze YES side
        yes_opportunity = self._analyze_side(market, "yes")
        no_opportunity = self._analyze_side(market, "no")

        # Return the better opportunity
        if yes_opportunity and no_opportunity:
            return yes_opportunity if yes_opportunity.perceived_edge > no_opportunity.perceived_edge else no_opportunity
        return yes_opportunity or no_opportunity

    def _analyze_side(self, market: PolymarketMarket, side: str) -> Optional[Opportunity]:
        """Analyze one side of a prediction market."""
        price = market.yes_price if side == "yes" else market.no_price
        bet_type = BetType.POLYMARKET_YES if side == "yes" else BetType.POLYMARKET_NO

        # Our fair value model (simple but effective... we hope)
        fair_value = self._estimate_fair_value(market, side)

        # Edge calculation
        edge = abs(fair_value - price)
        if edge < 0.03:  # Less than 3% edge, not worth the gas
            return None

        # Only bet if price is in our favor
        if side == "yes" and fair_value <= price:
            return None
        if side == "no" and fair_value <= (1 - price):
            return None

        # Confidence based on volume and edge size
        confidence = min(0.5 + (edge * 2) + (market.volume_24h / 500000) * 0.1, 0.90)

        # Momentum score (simplified - would use price history in production)
        momentum = self._calculate_momentum(market, side)

        # Time sensitivity
        time_sensitivity = self._calculate_time_sensitivity(market)

        return Opportunity(
            market_id=market.condition_id,
            market_name=f"[Poly] {market.question[:60]}",
            bet_type=bet_type,
            current_price=price,
            estimated_fair_value=fair_value,
            confidence=confidence,
            volume_24h=market.volume_24h,
            momentum_score=momentum,
            time_sensitivity=time_sensitivity,
            meta={
                "platform": "polymarket",
                "category": market.category,
                "liquidity": market.liquidity,
            },
        )

    def _estimate_fair_value(self, market: PolymarketMarket, side: str) -> float:
        """
        Estimate the 'true' fair value of a market outcome.

        This is where the magic (delusion) happens.
        In production, this would use:
        - News sentiment analysis
        - Historical accuracy of similar markets
        - External data feeds
        - Our gut feeling (most important)

        For now, we use a contrarian + momentum hybrid:
        - If price is extreme (< 0.15 or > 0.85), lean contrarian
        - If price is mid-range, lean momentum
        """
        price = market.yes_price if side == "yes" else market.no_price

        # Contrarian adjustment: extreme prices tend to mean-revert
        if price < 0.10:
            # "No way this resolves NO at 90%+ certainty" - us, possibly wrong
            adjustment = 0.08
        elif price > 0.90:
            # "Nothing is THAT certain" - us, definitely right sometimes
            adjustment = -0.05
        elif price < 0.25:
            adjustment = 0.05
        elif price > 0.75:
            adjustment = -0.03
        else:
            # Mid-range: slight momentum bias
            adjustment = 0.02 if market.volume_24h > 50000 else 0

        fair_value = price + adjustment

        # Add some structured randomness (our "intuition")
        # This represents information we "feel" but can't quantify
        import random
        intuition = random.gauss(0, 0.02)
        fair_value += intuition

        return max(min(fair_value, 0.99), 0.01)

    def _calculate_momentum(self, market: PolymarketMarket, side: str) -> float:
        """
        Calculate momentum score.

        In production: use orderbook depth and recent trades.
        For now: volume-based heuristic.
        """
        if market.volume_24h > 100000:
            return 0.3  # High volume = strong momentum signal
        elif market.volume_24h > 50000:
            return 0.15
        elif market.volume_24h > 10000:
            return 0.05
        return 0.0

    def _calculate_time_sensitivity(self, market: PolymarketMarket) -> float:
        """Markets close to expiry have higher time sensitivity."""
        # Simplified - would parse end_date in production
        return 0.1  # Default moderate sensitivity

    def get_orderbook(self, token_id: str) -> dict:
        """Fetch orderbook for a specific token."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/book",
                params={"token_id": token_id},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[Polymarket] Error fetching orderbook: {e}")
            return {"bids": [], "asks": []}

    def scan_for_opportunities(self) -> list[Opportunity]:
        """
        Main scanning function. Finds all current opportunities.

        Called periodically by the main agent loop.
        """
        markets = self.fetch_active_markets(limit=100)
        opportunities = []

        for market in markets:
            opp = self.analyze_market(market)
            if opp:
                opportunities.append(opp)

        # Sort by perceived edge
        opportunities.sort(key=lambda o: o.perceived_edge, reverse=True)

        return opportunities
