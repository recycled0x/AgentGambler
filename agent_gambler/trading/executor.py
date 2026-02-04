"""
Trade Executor - Where decisions become reality.

Handles:
- Order execution on Polymarket
- DEX swaps on Base chain via web3
- Transaction management
- The moment of truth when we click "send"

NOTE: Actual on-chain execution requires proper wallet setup.
This module provides the framework and simulation mode for testing.
"""

import time
import uuid
from dataclasses import dataclass
from typing import Optional

from web3 import Web3
from eth_account import Account

from agent_gambler.config import AgentConfig
from agent_gambler.strategies.gamblers_logic import BetDecision, BetType
from agent_gambler.trading.portfolio import PortfolioManager


@dataclass
class ExecutionResult:
    success: bool
    position_id: str
    tx_hash: Optional[str] = None
    executed_price: float = 0.0
    executed_size: float = 0.0
    fees: float = 0.0
    error: Optional[str] = None
    mode: str = "simulation"  # "simulation" or "live"


class TradeExecutor:
    """
    Executes trades across Polymarket and Base DEX.

    Supports two modes:
    - Simulation: Paper trading to test strategies without losing our precious $2
    - Live: Real execution on-chain (when we're feeling brave)
    """

    def __init__(self, config: AgentConfig, portfolio: PortfolioManager,
                 live_mode: bool = False):
        self.config = config
        self.portfolio = portfolio
        self.live_mode = live_mode
        self.w3: Optional[Web3] = None
        self.account = None

        if live_mode:
            self._init_web3()

    def _init_web3(self):
        """Initialize Web3 connection to Base chain."""
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.config.rpc.base_rpc_url))
            if self.config.wallet.private_key:
                self.account = Account.from_key(self.config.wallet.private_key)
                print(f"[Executor] Connected to Base. Wallet: {self.account.address}")
                balance = self.w3.eth.get_balance(self.account.address)
                eth_balance = self.w3.from_wei(balance, "ether")
                print(f"[Executor] ETH Balance: {eth_balance:.6f} ETH")
            else:
                print("[Executor] No private key configured. Read-only mode.")
        except Exception as e:
            print(f"[Executor] Web3 init failed: {e}. Falling back to simulation.")
            self.live_mode = False

    def execute_bet(self, decision: BetDecision) -> ExecutionResult:
        """
        Execute a bet decision.

        This is it. The moment. Let's make money.
        """
        position_id = f"pos_{uuid.uuid4().hex[:8]}"

        platform = decision.opportunity.meta.get("platform")
        
        if platform == "polymarket":
            return self._execute_polymarket(decision, position_id)
        elif platform == "base_dex":
            return self._execute_dex_swap(decision, position_id)
        elif platform == "solana_dex":
            return self._execute_solana_swap(decision, position_id)
        elif platform == "hyperliquid":
            return self._execute_perpetual(decision, position_id)
        else:
            return ExecutionResult(
                success=False,
                position_id=position_id,
                error=f"Unknown platform: {platform}",
            )

    def _execute_polymarket(self, decision: BetDecision,
                            position_id: str) -> ExecutionResult:
        """Execute a Polymarket order."""
        opp = decision.opportunity

        if self.live_mode:
            # Live Polymarket execution would go through their CLOB API
            # Requires API key authentication and signature
            return self._execute_polymarket_live(decision, position_id)

        # Simulation mode
        return self._simulate_execution(decision, position_id, slippage=0.02)

    def _execute_polymarket_live(self, decision: BetDecision,
                                 position_id: str) -> ExecutionResult:
        """
        Live Polymarket execution.

        TODO: Implement full CLOB API integration with:
        - API key authentication
        - Order signing
        - Order placement
        - Fill monitoring
        """
        # For now, return simulation with a note
        print("[Executor] Live Polymarket execution not yet implemented. Using simulation.")
        return self._simulate_execution(decision, position_id, slippage=0.02)

    def _execute_dex_swap(self, decision: BetDecision,
                          position_id: str) -> ExecutionResult:
        """Execute a DEX swap on Base chain."""
        if self.live_mode and self.w3 and self.account:
            return self._execute_dex_live(decision, position_id)

        # Simulation mode
        return self._simulate_execution(decision, position_id, slippage=0.03)

    def _execute_dex_live(self, decision: BetDecision,
                          position_id: str) -> ExecutionResult:
        """
        Live DEX execution on Base chain.

        Uses Uniswap V3 Router for token swaps.
        """
        opp = decision.opportunity
        token_address = opp.meta.get("token_address", "")

        if not token_address:
            return ExecutionResult(
                success=False,
                position_id=position_id,
                error="No token address provided",
            )

        try:
            # Calculate swap amount in ETH
            eth_price = self._get_eth_price_from_chain()
            if eth_price <= 0:
                return ExecutionResult(
                    success=False,
                    position_id=position_id,
                    error="Could not determine ETH price",
                )

            swap_amount_eth = decision.bet_size_usd / eth_price
            swap_amount_wei = self.w3.to_wei(swap_amount_eth, "ether")

            # Check balance
            balance = self.w3.eth.get_balance(self.account.address)
            if balance < swap_amount_wei:
                return ExecutionResult(
                    success=False,
                    position_id=position_id,
                    error=f"Insufficient ETH. Have: {self.w3.from_wei(balance, 'ether'):.6f}, "
                          f"Need: {swap_amount_eth:.6f}",
                )

            # Build swap transaction (Uniswap V3 exactInputSingle)
            # In production, this would construct the proper calldata
            print(f"[Executor] Would swap {swap_amount_eth:.6f} ETH for {opp.meta.get('symbol', '???')}")
            print(f"[Executor] Live DEX swaps require router ABI integration.")

            # For safety, fall back to simulation for now
            return self._simulate_execution(decision, position_id, slippage=0.03)

        except Exception as e:
            return ExecutionResult(
                success=False,
                position_id=position_id,
                error=f"DEX execution error: {e}",
            )

    def _simulate_execution(self, decision: BetDecision, position_id: str,
                            slippage: float = 0.02) -> ExecutionResult:
        """
        Simulate trade execution with realistic slippage.

        Good for testing without risking our sacred $2.
        """
        opp = decision.opportunity

        # Simulate slippage (usually against us, because of course)
        import random
        slip = random.uniform(0, slippage)
        if opp.bet_type in (BetType.POLYMARKET_YES, BetType.DEX_LONG, BetType.SOLANA_LONG, 
                           BetType.PERP_LONG, BetType.HYPERLIQUID_LONG):
            executed_price = opp.current_price * (1 + slip)
        else:
            executed_price = opp.current_price * (1 - slip)

        # Simulate fees
        platform = opp.meta.get("platform", "")
        if platform == "base_dex":
            fee_rate = 0.003
        elif platform == "solana_dex":
            fee_rate = 0.001  # Solana fees are lower
        elif platform == "hyperliquid":
            fee_rate = 0.0002  # Perp fees are very low
        else:
            fee_rate = 0.002
        
        fees = decision.bet_size_usd * fee_rate
        actual_size = decision.bet_size_usd - fees

        # Open position in portfolio
        side = "yes" if opp.bet_type == BetType.POLYMARKET_YES else \
               "no" if opp.bet_type == BetType.POLYMARKET_NO else \
               "long" if opp.bet_type in (BetType.DEX_LONG, BetType.SOLANA_LONG, 
                                         BetType.PERP_LONG, BetType.HYPERLIQUID_LONG) else "short"
        
        # For perpetuals, extract leverage from meta or use default
        leverage = None
        if platform == "hyperliquid":
            leverage = min(opp.meta.get("max_leverage", 20.0), 
                          self.config.perpetuals.max_leverage)

        self.portfolio.open_position(
            position_id=position_id,
            platform=opp.meta.get("platform", "unknown"),
            market_id=opp.market_id,
            market_name=opp.market_name,
            side=side,
            entry_price=executed_price,
            size_usd=actual_size,
            stop_loss=decision.stop_loss_price,
            leverage=leverage,
        )

        self.portfolio.total_fees_paid += fees

        return ExecutionResult(
            success=True,
            position_id=position_id,
            tx_hash=f"0xSIM_{uuid.uuid4().hex[:16]}",
            executed_price=executed_price,
            executed_size=actual_size,
            fees=fees,
            mode="simulation",
        )

    def _get_eth_price_from_chain(self) -> float:
        """Get ETH price from on-chain oracle or pool."""
        # Simplified - would use Chainlink oracle or pool price
        try:
            import requests
            resp = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "ethereum", "vs_currencies": "usd"},
                timeout=10,
            )
            return resp.json()["ethereum"]["usd"]
        except Exception:
            return 0.0

    def _execute_solana_swap(self, decision: BetDecision,
                             position_id: str) -> ExecutionResult:
        """Execute a Solana DEX swap via Jupiter."""
        # For now, use simulation mode
        # In production, would use Jupiter SDK or direct API calls
        return self._simulate_execution(decision, position_id, slippage=0.02)

    def _execute_perpetual(self, decision: BetDecision,
                           position_id: str) -> ExecutionResult:
        """Execute a perpetual futures trade on Hyperliquid."""
        # For now, use simulation mode
        # In production, would use Hyperliquid REST API
        return self._simulate_execution(decision, position_id, slippage=0.001)

    def close_position(self, position_id: str, exit_price: float,
                       reason: str = "manual") -> Optional[ExecutionResult]:
        """Close an existing position."""
        record = self.portfolio.close_position(position_id, exit_price, reason)
        if record:
            return ExecutionResult(
                success=True,
                position_id=position_id,
                executed_price=exit_price,
                executed_size=record.size_usd,
                mode="simulation" if not self.live_mode else "live",
            )
        return None
