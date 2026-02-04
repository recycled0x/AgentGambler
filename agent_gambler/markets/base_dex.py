"""
Base Chain DEX Trading Module.

Trade ETH and tokens on Base L2 using Uniswap V3 / Aerodrome pools.
Low fees, fast execution, perfect for a $2 bankroll that's going to $2M.

Focus areas:
- ETH/USDC swaps for taking positions
- Meme coin momentum trades (high risk, higher reward)
- Liquidity sniping on new pairs
- Arbitrage between pools (if we're fast enough)
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import requests

from agent_gambler.strategies.gamblers_logic import BetType, Opportunity


# Key Base chain contract addresses
BASE_CONTRACTS = {
    "WETH": "0x4200000000000000000000000000000000000006",
    "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
    "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
    "AERO": "0x940181a94A35A4569E4529A3CDfB74e38FD98631",
    "UNISWAP_V3_ROUTER": "0x2626664c2603336E57B271c5C0b26F421741e481",
    "UNISWAP_V3_FACTORY": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
    "AERODROME_ROUTER": "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
}

# Tokens we're interested in sniping/trading
WATCHLIST_TOKENS = {
    "BRETT": "0x532f27101965dd16442E59d40670FaF5eBB142E4",
    "DEGEN": "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed",
    "TOSHI": "0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4",
    "HIGHER": "0x0578d8A44db98B23BF096A382e016e29a5Ce0ffe",
}


@dataclass
class TokenInfo:
    address: str
    symbol: str
    name: str
    price_usd: float
    price_change_24h: float  # Percentage
    volume_24h: float
    liquidity_usd: float
    market_cap: float = 0.0


@dataclass
class PoolInfo:
    pool_address: str
    token0: str
    token1: str
    fee_tier: int
    tvl_usd: float
    volume_24h: float
    price: float
    tick_current: int = 0


class BaseDEXClient:
    """
    Client for trading on Base chain DEXes.

    Strategy: Find momentum, ride it. Find dips, buy them.
    Find new listings, ape in. This is the way to $2M.
    """

    DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })
        self._price_cache = {}
        self._cache_timestamp = 0

    def fetch_token_info(self, token_address: str) -> Optional[TokenInfo]:
        """Fetch token info from DexScreener API."""
        try:
            response = self.session.get(
                f"{self.DEXSCREENER_API}/tokens/{token_address}",
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("pairs"):
                return None

            # Use the highest liquidity pair
            pair = max(data["pairs"], key=lambda p: float(p.get("liquidity", {}).get("usd", 0)))

            return TokenInfo(
                address=token_address,
                symbol=pair.get("baseToken", {}).get("symbol", "???"),
                name=pair.get("baseToken", {}).get("name", "Unknown"),
                price_usd=float(pair.get("priceUsd", 0)),
                price_change_24h=float(pair.get("priceChange", {}).get("h24", 0)),
                volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                liquidity_usd=float(pair.get("liquidity", {}).get("usd", 0)),
                market_cap=float(pair.get("fdv", 0)),
            )

        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[BaseDEX] Error fetching token info for {token_address}: {e}")
            return None

    def scan_base_pairs(self, min_liquidity: float = 5000) -> list[TokenInfo]:
        """
        Scan Base chain for tradeable pairs.

        Focus on:
        - Established tokens with liquidity
        - New tokens with momentum (meme coin meta)
        - Tokens with unusual volume spikes
        """
        tokens = []

        # Check watchlist tokens
        for symbol, address in WATCHLIST_TOKENS.items():
            info = self.fetch_token_info(address)
            if info and info.liquidity_usd >= min_liquidity:
                tokens.append(info)

        # Search for trending Base pairs
        try:
            response = self.session.get(
                f"{self.DEXSCREENER_API}/search",
                params={"q": "base"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            for pair in data.get("pairs", [])[:20]:
                if pair.get("chainId") != "base":
                    continue
                liquidity = float(pair.get("liquidity", {}).get("usd", 0))
                if liquidity < min_liquidity:
                    continue

                token = TokenInfo(
                    address=pair.get("baseToken", {}).get("address", ""),
                    symbol=pair.get("baseToken", {}).get("symbol", "???"),
                    name=pair.get("baseToken", {}).get("name", "Unknown"),
                    price_usd=float(pair.get("priceUsd", 0)),
                    price_change_24h=float(pair.get("priceChange", {}).get("h24", 0)),
                    volume_24h=float(pair.get("volume", {}).get("h24", 0)),
                    liquidity_usd=liquidity,
                    market_cap=float(pair.get("fdv", 0)),
                )
                tokens.append(token)

        except requests.RequestException as e:
            print(f"[BaseDEX] Error scanning pairs: {e}")

        return tokens

    def analyze_token(self, token: TokenInfo) -> Optional[Opportunity]:
        """
        Analyze a token for trading opportunities.

        Signals:
        1. Momentum: > 10% gain in 24h with volume = ride the wave
        2. Dip buy: > 20% drop with high volume = potential reversal
        3. Volume spike: unusual volume = something is happening
        4. New listing pump: fresh token + volume = ape carefully
        """
        if token.price_usd <= 0 or token.liquidity_usd < 5000:
            return None

        # Determine trade direction and confidence
        bet_type = None
        fair_value = token.price_usd
        confidence = 0.5

        price_change = token.price_change_24h

        # MOMENTUM PLAY: Strong uptrend
        if price_change > 15:
            bet_type = BetType.DEX_LONG
            # Momentum target: expect 30-50% of current move to continue
            fair_value = token.price_usd * (1 + (price_change / 100) * 0.35)
            confidence = min(0.55 + (token.volume_24h / 1000000) * 0.1, 0.80)
            momentum = min(price_change / 100, 1.0)

        # DIP BUY: Sharp drop with volume (the "it can't go lower" play)
        elif price_change < -20 and token.volume_24h > 20000:
            bet_type = BetType.DEX_LONG
            # Mean reversion target: expect 40% recovery
            fair_value = token.price_usd * (1 + abs(price_change / 100) * 0.40)
            confidence = 0.50 + min(token.volume_24h / 500000, 0.15)
            momentum = -0.3  # Against momentum but we're contrarian here

        # VOLUME SPIKE: Unusual activity
        elif token.volume_24h > token.liquidity_usd * 2:
            bet_type = BetType.DEX_LONG
            fair_value = token.price_usd * 1.15  # Conservative 15% target
            confidence = 0.55
            momentum = 0.2

        # STEADY GROWER: Moderate gains + solid volume
        elif 5 < price_change < 15 and token.volume_24h > 50000:
            bet_type = BetType.DEX_LONG
            fair_value = token.price_usd * 1.10
            confidence = 0.55
            momentum = 0.15

        else:
            return None  # No clear signal, pass

        edge = abs(fair_value - token.price_usd) / token.price_usd
        if edge < 0.05:  # Less than 5% expected move, not worth it
            return None

        return Opportunity(
            market_id=token.address,
            market_name=f"[Base] {token.symbol} ({token.name[:30]})",
            bet_type=bet_type,
            current_price=token.price_usd,
            estimated_fair_value=fair_value,
            confidence=confidence,
            volume_24h=token.volume_24h,
            momentum_score=momentum if 'momentum' in dir() else 0.0,
            time_sensitivity=0.3,  # DEX trades are moderately time-sensitive
            meta={
                "platform": "base_dex",
                "token_address": token.address,
                "symbol": token.symbol,
                "liquidity": token.liquidity_usd,
                "market_cap": token.market_cap,
                "price_change_24h": price_change,
            },
        )

    def scan_for_opportunities(self) -> list[Opportunity]:
        """
        Main scanning function for Base DEX opportunities.

        The degen scanner. Finds momentum, dips, and ape-worthy tokens.
        """
        tokens = self.scan_base_pairs()
        opportunities = []

        for token in tokens:
            opp = self.analyze_token(token)
            if opp:
                opportunities.append(opp)

        # Sort by perceived edge
        opportunities.sort(key=lambda o: o.perceived_edge, reverse=True)

        return opportunities

    def get_eth_price(self) -> float:
        """Get current ETH price in USD."""
        try:
            info = self.fetch_token_info(BASE_CONTRACTS["WETH"])
            if info:
                return info.price_usd
        except Exception:
            pass

        # Fallback: use a simple API
        try:
            response = self.session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
                timeout=10,
            )
            return response.json()["ethereum"]["usd"]
        except Exception:
            return 0.0
