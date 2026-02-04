"""
Portfolio Manager - Tracks our journey from $2 to $2M.

Manages:
- Position tracking across Polymarket and Base DEX
- P&L calculation
- Risk exposure monitoring
- The emotional rollercoaster of degenerate trading
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Position:
    position_id: str
    platform: str  # "polymarket", "base_dex", "solana_dex", "hyperliquid"
    market_id: str
    market_name: str
    side: str  # "yes", "no", "long", "short"
    entry_price: float
    current_price: float
    size_usd: float
    quantity: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_time: float = field(default_factory=time.time)
    status: str = "open"  # "open", "closed", "stopped_out"
    leverage: Optional[float] = None  # For perpetual positions
    liquidation_price: Optional[float] = None  # For perpetual positions
    funding_rate: float = 0.0  # Current funding rate for perps

    @property
    def unrealized_pnl(self) -> float:
        if self.side in ("yes", "long"):
            pnl = (self.current_price - self.entry_price) * self.quantity
        else:
            pnl = (self.entry_price - self.current_price) * self.quantity
        
        # Apply leverage multiplier for perpetuals
        if self.leverage and self.leverage > 1.0:
            pnl *= self.leverage
        
        return pnl

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.size_usd == 0:
            return 0.0
        return (self.unrealized_pnl / self.size_usd) * 100

    @property
    def hold_duration_mins(self) -> float:
        return (time.time() - self.entry_time) / 60


@dataclass
class TradeRecord:
    position_id: str
    platform: str
    market_name: str
    side: str
    entry_price: float
    exit_price: float
    size_usd: float
    realized_pnl: float
    realized_pnl_pct: float
    hold_duration_mins: float
    entry_time: str
    exit_time: str
    rationale: str = ""
    exit_reason: str = ""  # "take_profit", "stop_loss", "manual", "expired"


class PortfolioManager:
    """
    Tracks every dollar on its journey to becoming a million.

    Features:
    - Position management
    - P&L tracking
    - Risk monitoring
    - Trade journal (for the documentary about how we turned $2 into $2M)
    """

    def __init__(self, config):
        self.config = config
        self.positions: dict[str, Position] = {}
        self.trade_history: list[TradeRecord] = []
        self.starting_balance = config.trading.starting_capital_usd
        self.current_balance = config.trading.starting_capital_usd
        self.total_realized_pnl = 0.0
        self.total_fees_paid = 0.0
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)

    @property
    def total_exposure(self) -> float:
        """Total USD value in open positions (collateral for leveraged positions)."""
        exposure = 0.0
        for p in self.positions.values():
            if p.status == "open":
                if p.leverage and p.leverage > 1.0:
                    # For leveraged positions, exposure is collateral + unrealized P&L
                    collateral = p.size_usd / p.leverage
                    exposure += collateral + p.unrealized_pnl
                else:
                    exposure += p.size_usd + p.unrealized_pnl
        return exposure

    @property
    def available_balance(self) -> float:
        """Cash available for new bets."""
        return self.current_balance - self.total_exposure

    @property
    def total_portfolio_value(self) -> float:
        """Total value: cash + positions."""
        return self.current_balance + sum(
            p.unrealized_pnl for p in self.positions.values() if p.status == "open"
        )

    @property
    def total_return_pct(self) -> float:
        """Total return percentage from starting capital."""
        if self.starting_balance == 0:
            return 0.0
        return ((self.total_portfolio_value - self.starting_balance) / self.starting_balance) * 100

    @property
    def win_count(self) -> int:
        return sum(1 for t in self.trade_history if t.realized_pnl > 0)

    @property
    def loss_count(self) -> int:
        return sum(1 for t in self.trade_history if t.realized_pnl <= 0)

    @property
    def win_rate(self) -> float:
        total = len(self.trade_history)
        if total == 0:
            return 0.0
        return self.win_count / total

    @property
    def largest_win(self) -> float:
        if not self.trade_history:
            return 0.0
        return max(t.realized_pnl for t in self.trade_history)

    @property
    def largest_loss(self) -> float:
        if not self.trade_history:
            return 0.0
        return min(t.realized_pnl for t in self.trade_history)

    @property
    def avg_win(self) -> float:
        wins = [t.realized_pnl for t in self.trade_history if t.realized_pnl > 0]
        return sum(wins) / len(wins) if wins else 0.0

    @property
    def avg_loss(self) -> float:
        losses = [t.realized_pnl for t in self.trade_history if t.realized_pnl <= 0]
        return sum(losses) / len(losses) if losses else 0.0

    @property
    def profit_factor(self) -> float:
        """Gross profits / gross losses. > 1 means we're winning."""
        gross_profit = sum(t.realized_pnl for t in self.trade_history if t.realized_pnl > 0)
        gross_loss = abs(sum(t.realized_pnl for t in self.trade_history if t.realized_pnl < 0))
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    def open_position(self, position_id: str, platform: str, market_id: str,
                      market_name: str, side: str, entry_price: float,
                      size_usd: float, stop_loss: Optional[float] = None,
                      take_profit: Optional[float] = None,
                      leverage: Optional[float] = None,
                      liquidation_price: Optional[float] = None) -> Position:
        """Open a new position. Another step on the road to $2M."""
        quantity = size_usd / entry_price if entry_price > 0 else 0

        position = Position(
            position_id=position_id,
            platform=platform,
            market_id=market_id,
            market_name=market_name,
            side=side,
            entry_price=entry_price,
            current_price=entry_price,
            size_usd=size_usd,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            leverage=leverage,
            liquidation_price=liquidation_price,
        )

        self.positions[position_id] = position
        # For leveraged positions, only lock up collateral, not full position size
        collateral = size_usd / leverage if leverage and leverage > 1.0 else size_usd
        self.current_balance -= collateral

        return position

    def close_position(self, position_id: str, exit_price: float,
                       exit_reason: str = "manual") -> Optional[TradeRecord]:
        """Close a position and record the trade."""
        position = self.positions.get(position_id)
        if not position or position.status != "open":
            return None

        position.current_price = exit_price
        position.status = "closed"

        pnl = position.unrealized_pnl
        pnl_pct = position.unrealized_pnl_pct

        # Return capital + profit (or minus loss)
        # For leveraged positions, return collateral + leveraged P&L
        if position.leverage and position.leverage > 1.0:
            collateral = position.size_usd / position.leverage
            self.current_balance += collateral + pnl
        else:
            self.current_balance += position.size_usd + pnl
        self.total_realized_pnl += pnl

        record = TradeRecord(
            position_id=position_id,
            platform=position.platform,
            market_name=position.market_name,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            size_usd=position.size_usd,
            realized_pnl=pnl,
            realized_pnl_pct=pnl_pct,
            hold_duration_mins=position.hold_duration_mins,
            entry_time=datetime.fromtimestamp(position.entry_time).isoformat(),
            exit_time=datetime.now().isoformat(),
            exit_reason=exit_reason,
        )

        self.trade_history.append(record)

        return record

    def update_position_price(self, position_id: str, current_price: float):
        """Update the current price of a position."""
        if position_id in self.positions:
            self.positions[position_id].current_price = current_price

    def check_stop_losses(self) -> list[str]:
        """Check all positions for stop loss triggers. Returns IDs to close."""
        to_close = []
        for pid, pos in self.positions.items():
            if pos.status != "open" or pos.stop_loss is None:
                continue

            if pos.side in ("yes", "long") and pos.current_price <= pos.stop_loss:
                to_close.append(pid)
            elif pos.side in ("no", "short") and pos.current_price >= pos.stop_loss:
                to_close.append(pid)

        return to_close

    def get_portfolio_summary(self) -> dict:
        """Get a complete portfolio summary for display."""
        open_positions = [p for p in self.positions.values() if p.status == "open"]

        return {
            "total_value": f"${self.total_portfolio_value:.2f}",
            "cash_balance": f"${self.current_balance:.2f}",
            "total_exposure": f"${self.total_exposure:.2f}",
            "available": f"${self.available_balance:.2f}",
            "total_return": f"{self.total_return_pct:+.1f}%",
            "realized_pnl": f"${self.total_realized_pnl:+.2f}",
            "unrealized_pnl": f"${sum(p.unrealized_pnl for p in open_positions):+.2f}",
            "open_positions": len(open_positions),
            "total_trades": len(self.trade_history),
            "win_rate": f"{self.win_rate:.1%}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "largest_win": f"${self.largest_win:+.2f}",
            "largest_loss": f"${self.largest_loss:+.2f}",
            "target": f"${self.config.trading.moonshot_target_usd:,.0f}",
            "progress": f"{(self.total_portfolio_value / self.config.trading.moonshot_target_usd) * 100:.6f}%",
        }

    def save_state(self):
        """Save portfolio state to disk."""
        state = {
            "current_balance": self.current_balance,
            "total_realized_pnl": self.total_realized_pnl,
            "total_fees_paid": self.total_fees_paid,
            "positions": {
                pid: {
                    "position_id": p.position_id,
                    "platform": p.platform,
                    "market_id": p.market_id,
                    "market_name": p.market_name,
                    "side": p.side,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "size_usd": p.size_usd,
                    "quantity": p.quantity,
                    "stop_loss": p.stop_loss,
                    "entry_time": p.entry_time,
                    "status": p.status,
                    "leverage": p.leverage,
                    "liquidation_price": p.liquidation_price,
                    "funding_rate": p.funding_rate,
                }
                for pid, p in self.positions.items()
            },
            "trade_count": len(self.trade_history),
        }

        with open(self.data_dir / "portfolio_state.json", "w") as f:
            json.dump(state, f, indent=2)

    def load_state(self):
        """Load portfolio state from disk."""
        state_file = self.data_dir / "portfolio_state.json"
        if not state_file.exists():
            return

        with open(state_file) as f:
            state = json.load(f)

        self.current_balance = state.get("current_balance", self.starting_balance)
        self.total_realized_pnl = state.get("total_realized_pnl", 0.0)
        self.total_fees_paid = state.get("total_fees_paid", 0.0)

        for pid, pdata in state.get("positions", {}).items():
            # Handle missing fields for backward compatibility
            pdata.setdefault("leverage", None)
            pdata.setdefault("liquidation_price", None)
            pdata.setdefault("funding_rate", 0.0)
            self.positions[pid] = Position(**pdata)
