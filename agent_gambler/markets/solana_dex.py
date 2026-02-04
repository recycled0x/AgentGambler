"""
Solana DEX Trading Module.

Trade SOL and tokens on Solana using Jupiter Aggregator + direct DEX APIs.
Fast, cheap, perfect for degen plays.

Focus areas:
- Jupiter Aggregator for best-price routing
- Direct DEX APIs (Raydium, Orca) for market scanning
- Meme coin momentum trades (BONK, WIF, POPCAT, etc.)
- New token sniping opportunities
"""

import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import requests

from agent_gambler.strategies.gamblers_logic import BetType, Opportunity


# Key Solana token addresses
SOLANA_TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "BONK": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",
    "POPCAT": "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr",
    "JTO": "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",
}

# DexScreener API for Solana pairs
DEXSCREENER_SOLANA_API = "https://api.dexscreener.com/latest/dex"


@dataclass
class SolanaTokenInfo:
    address: str
    symbol: str
    name: str
    price_usd: float
    price_change_24h: float  # Percentage
    volume_24h: float
    liquidity_usd: float
    market_cap: float = 0.0


class SolanaDEXClient:
    """
    Client for trading on Solana DEXes via Jupiter Aggregator.

    Strategy: Find momentum, execute fast. Find dips, buy them.
    Find new listings, ape in. This is the way to $2M.
    """

    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })
        self._price_cache = {}
        self._cache_timestamp = 0

    def fetch_token_info(self, token_address: str) -> Optional[SolanaTokenInfo]:
        """Fetch token info from DexScreener API."""
        try:
            response = self.session.get(
                f"{DEXSCREENER_SOLANA_API}/tokens/{token_address}",
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("pairs"):
                return None

            # Use the highest liquidity pair
            pair = max(data["pairs"], key=lambda p: float(p.get("liquidity", {}).get("usd", 0)))

            return SolanaTokenInfo(
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
            print(f"[SolanaDEX] Error fetching token info for {token_address}: {e}")
            return None

    def scan_solana_pairs(self, min_liquidity: float = 5000) -> list[SolanaTokenInfo]:
        """
        Scan Solana chain for tradeable pairs.

        Focus on:
        - Established tokens with liquidity
        - New tokens with momentum (meme coin meta)
        - Tokens with unusual volume spikes
        """
        tokens = []

        # Check watchlist tokens
        for symbol, address in SOLANA_TOKENS.items():
            if symbol == "SOL":  # Skip SOL itself
                continue
            info = self.fetch_token_info(address)
            if info and info.liquidity_usd >= min_liquidity:
                tokens.append(info)

        # Search for trending Solana pairs
        try:
            response = self.session.get(
                f"{DEXSCREENER_SOLANA_API}/search",
                params={"q": "solana"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            for pair in data.get("pairs", [])[:30]:
                if pair.get("chainId") != "solana":
                    continue
                liquidity = float(pair.get("liquidity", {}).get("usd", 0))
                if liquidity < min_liquidity:
                    continue

                token = SolanaTokenInfo(
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
            print(f"[SolanaDEX] Error scanning pairs: {e}")

        return tokens

    def get_jupiter_quote(self, input_mint: str, output_mint: str, amount: int, slippage_bps: int = 50) -> Optional[dict]:
        """
        Get a quote from Jupiter Aggregator for a swap.

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount in smallest unit (lamports for SOL)
            slippage_bps: Slippage in basis points (default 0.5%)
        """
        try:
            response = self.session.get(
                f"{self.config.solana.jupiter_api_url}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": amount,
                    "slippageBps": slippage_bps,
                },
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"[SolanaDEX] Error getting Jupiter quote: {e}")
            return None

    def analyze_token(self, token: SolanaTokenInfo) -> Optional[Opportunity]:
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
            bet_type = BetType.SOLANA_LONG
            # Momentum target: expect 30-50% of current move to continue
            fair_value = token.price_usd * (1 + (price_change / 100) * 0.35)
            confidence = min(0.55 + (token.volume_24h / 1000000) * 0.1, 0.80)
            momentum = min(price_change / 100, 1.0)

        # DIP BUY: Sharp drop with volume (the "it can't go lower" play)
        elif price_change < -20 and token.volume_24h > 20000:
            bet_type = BetType.SOLANA_LONG
            # Mean reversion target: expect 40% recovery
            fair_value = token.price_usd * (1 + abs(price_change / 100) * 0.40)
            confidence = 0.50 + min(token.volume_24h / 500000, 0.15)
            momentum = -0.3  # Against momentum but we're contrarian here

        # VOLUME SPIKE: Unusual activity
        elif token.volume_24h > token.liquidity_usd * 2:
            bet_type = BetType.SOLANA_LONG
            fair_value = token.price_usd * 1.15  # Conservative 15% target
            confidence = 0.55
            momentum = 0.2

        # STEADY GROWER: Moderate gains + solid volume
        elif 5 < price_change < 15 and token.volume_24h > 50000:
            bet_type = BetType.SOLANA_LONG
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
            market_name=f"[Solana] {token.symbol} ({token.name[:30]})",
            bet_type=bet_type,
            current_price=token.price_usd,
            estimated_fair_value=fair_value,
            confidence=confidence,
            volume_24h=token.volume_24h,
            momentum_score=momentum if 'momentum' in dir() else 0.0,
            time_sensitivity=0.3,  # DEX trades are moderately time-sensitive
            meta={
                "platform": "solana_dex",
                "token_address": token.address,
                "symbol": token.symbol,
                "liquidity": token.liquidity_usd,
                "market_cap": token.market_cap,
                "price_change_24h": price_change,
            },
        )

    def scan_for_opportunities(self) -> list[Opportunity]:
        """
        Main scanning function for Solana DEX opportunities.

        The degen scanner. Finds momentum, dips, and ape-worthy tokens.
        """
        tokens = self.scan_solana_pairs()
        opportunities = []

        for token in tokens:
            opp = self.analyze_token(token)
            if opp:
                opportunities.append(opp)

        # Sort by perceived edge
        opportunities.sort(key=lambda o: o.perceived_edge, reverse=True)

        return opportunities

    def get_sol_price(self) -> float:
        """Get current SOL price in USD."""
        try:
            info = self.fetch_token_info(SOLANA_TOKENS["SOL"])
            if info:
                return info.price_usd
        except Exception:
            pass

        # Fallback: use a simple API
        try:
            response = self.session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"},
                timeout=10,
            )
            return response.json()["solana"]["usd"]
        except Exception:
            return 0.0
