"""
Configuration for the AgentGambler.

We start with $2. We end with $2M. Everything in between is just vibes.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class WalletConfig:
    private_key: str = os.getenv("PRIVATE_KEY", "")
    wallet_address: str = os.getenv("WALLET_ADDRESS", "")


@dataclass
class RPCConfig:
    base_rpc_url: str = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
    eth_rpc_url: str = os.getenv("ETH_RPC_URL", "https://eth.llamarpc.com")


@dataclass
class PolymarketConfig:
    api_url: str = os.getenv("POLYMARKET_API_URL", "https://clob.polymarket.com")
    chain_id: int = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))


@dataclass
class SolanaConfig:
    rpc_url: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    jupiter_api_url: str = "https://quote-api.jup.ag/v6"
    private_key: str = os.getenv("SOLANA_PRIVATE_KEY", "")


@dataclass
class PerpetualsConfig:
    hyperliquid_api_url: str = "https://api.hyperliquid.xyz"
    max_leverage: float = float(os.getenv("MAX_LEVERAGE", "5.0"))
    funding_rate_threshold: float = 0.0001  # 0.01% per 8h
    liquidation_buffer: float = 0.10  # 10% buffer before liquidation


@dataclass
class TradingConfig:
    starting_capital_usd: float = float(os.getenv("STARTING_CAPITAL_USD", "2.00"))
    moonshot_target_usd: float = float(os.getenv("MOONSHOT_TARGET_USD", "2000000.00"))
    max_single_bet_pct: float = float(os.getenv("MAX_SINGLE_BET_PCT", "0.25"))
    stop_loss_pct: float = float(os.getenv("STOP_LOSS_PCT", "0.15"))
    kelly_fraction: float = float(os.getenv("KELLY_FRACTION", "0.5"))
    compound_wins: bool = True  # Always let it ride
    min_edge_threshold: float = 0.05  # Minimum perceived edge to enter


@dataclass
class AgentConfig:
    wallet: WalletConfig = field(default_factory=WalletConfig)
    rpc: RPCConfig = field(default_factory=RPCConfig)
    polymarket: PolymarketConfig = field(default_factory=PolymarketConfig)
    solana: SolanaConfig = field(default_factory=SolanaConfig)
    perpetuals: PerpetualsConfig = field(default_factory=PerpetualsConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    optimism_level: str = os.getenv("OPTIMISM_LEVEL", "DELUSIONAL")

    @property
    def multiplier_needed(self) -> float:
        return self.trading.moonshot_target_usd / self.trading.starting_capital_usd

    @property
    def doublings_needed(self) -> int:
        """Only ~20 doublings from $2 to $2M. Easy."""
        import math
        return math.ceil(math.log2(self.multiplier_needed))
