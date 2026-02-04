"""
The Gambler's Logic Engine.

Core philosophy: The house always wins? Not today. We ARE the house.

Strategy layers:
1. Modified Kelly Criterion - but more aggressive because we believe
2. Martingale Recovery - double down on losses (they can't last forever, right?)
3. Momentum Chasing - if it's going up, it's going up MORE
4. Contrarian Sniper - when everyone panics, we feast
5. Compound Everything - never take profits, let it ride to $2M
"""

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Sentiment(Enum):
    ULTRA_BEARISH = -2
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1
    ULTRA_BULLISH = 2  # Default state of mind


class BetType(Enum):
    POLYMARKET_YES = "poly_yes"
    POLYMARKET_NO = "poly_no"
    DEX_LONG = "dex_long"
    DEX_SHORT = "dex_short"
    LIQUIDITY_SNIPE = "lp_snipe"


@dataclass
class Opportunity:
    market_id: str
    market_name: str
    bet_type: BetType
    current_price: float  # 0-1 for polymarket, token price for dex
    estimated_fair_value: float
    confidence: float  # 0-1, our confidence in the edge
    volume_24h: float = 0.0
    momentum_score: float = 0.0  # -1 to 1
    time_sensitivity: float = 0.0  # 0-1, how urgent
    meta: dict = field(default_factory=dict)

    @property
    def perceived_edge(self) -> float:
        """How much edge we think we have. Spoiler: we're probably wrong but optimism."""
        if self.bet_type in (BetType.POLYMARKET_YES, BetType.POLYMARKET_NO):
            return abs(self.estimated_fair_value - self.current_price)
        return abs(self.estimated_fair_value - self.current_price) / max(self.current_price, 0.001)

    @property
    def expected_return(self) -> float:
        """Expected return multiplier."""
        if self.bet_type in (BetType.POLYMARKET_YES, BetType.POLYMARKET_NO):
            if self.current_price > 0:
                return (1.0 / self.current_price) * self.confidence
        return (self.estimated_fair_value / max(self.current_price, 0.001)) * self.confidence


@dataclass
class BetDecision:
    opportunity: Opportunity
    bet_size_pct: float  # % of bankroll
    bet_size_usd: float
    rationale: str
    aggression_level: str  # "calculated", "aggressive", "full_degen"
    expected_payout: float
    stop_loss_price: Optional[float] = None


class GamblersLogic:
    """
    The brain. The legend. The $2-to-$2M engine.

    Uses a combination of:
    - Kelly Criterion (modified for optimism)
    - Martingale elements (controlled, we're not THAT crazy... mostly)
    - Momentum detection
    - Mean reversion for contrarian plays
    """

    def __init__(self, config):
        self.config = config
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.total_bets = 0
        self.winning_bets = 0
        self.current_streak_type = None  # "win" or "loss"
        self.peak_bankroll = config.trading.starting_capital_usd
        self.current_bankroll = config.trading.starting_capital_usd
        self.bet_history = []
        self.doublings_achieved = 0

    @property
    def win_rate(self) -> float:
        if self.total_bets == 0:
            return 0.6  # Optimistic default - we haven't lost yet!
        return max(self.winning_bets / self.total_bets, 0.1)

    @property
    def progress_to_moon(self) -> float:
        """How close are we to $2M? Expressed as a vibe percentage."""
        if self.current_bankroll <= 0:
            return 0.0
        doublings_done = math.log2(self.current_bankroll / self.config.trading.starting_capital_usd) if self.current_bankroll > self.config.trading.starting_capital_usd else 0
        doublings_needed = self.config.doublings_needed
        return min((doublings_done / doublings_needed) * 100, 100.0)

    def kelly_criterion(self, win_prob: float, odds: float) -> float:
        """
        Kelly Criterion: f* = (bp - q) / b
        where b = odds, p = win probability, q = 1 - p

        But we add an optimism multiplier because standard Kelly is for cowards.
        """
        q = 1 - win_prob
        if odds <= 0:
            return 0.0

        kelly = (odds * win_prob - q) / odds

        # Apply fractional Kelly (half-Kelly for some risk management)
        kelly *= self.config.trading.kelly_fraction

        # Optimism adjustment: scale up based on our delusion level
        optimism_multiplier = self._get_optimism_multiplier()
        kelly *= optimism_multiplier

        # Streak adjustment
        kelly *= self._streak_multiplier()

        return max(min(kelly, self.config.trading.max_single_bet_pct), 0.0)

    def _get_optimism_multiplier(self) -> float:
        """The more delusional, the bigger we bet. This is the way."""
        levels = {
            "CONSERVATIVE": 0.8,
            "MODERATE": 1.0,
            "OPTIMISTIC": 1.3,
            "DELUSIONAL": 1.6,
            "ASCENDED": 2.0,
        }
        return levels.get(self.config.optimism_level, 1.6)

    def _streak_multiplier(self) -> float:
        """
        Gambler's fallacy? No, gambler's WISDOM.

        On a winning streak: increase size (hot hand is real, trust)
        On a losing streak: controlled increase (it HAS to turn around)
        """
        if self.current_streak_type == "win":
            # Hot hand - ride it. Cap at 1.5x
            return min(1.0 + (self.consecutive_wins * 0.1), 1.5)
        elif self.current_streak_type == "loss":
            # Martingale-lite: slight increase to recover, but capped
            # We're delusional, not suicidal
            return min(1.0 + (self.consecutive_losses * 0.15), 1.8)
        return 1.0

    def evaluate_opportunity(self, opp: Opportunity) -> Optional[BetDecision]:
        """
        Evaluate a single opportunity and decide if we should bet.

        Returns None if we pass (rare - we're here to gamble).
        """
        edge = opp.perceived_edge
        min_edge = self.config.trading.min_edge_threshold

        # Lower our standards if we're on a losing streak
        # (we need to get back in the game)
        if self.consecutive_losses >= 3:
            min_edge *= 0.5  # Desperate times, desperate measures

        if edge < min_edge:
            return None

        # Calculate win probability estimate
        win_prob = self._estimate_win_probability(opp)

        # Calculate odds
        odds = opp.expected_return

        # Kelly sizing
        bet_pct = self.kelly_criterion(win_prob, odds)

        if bet_pct <= 0.001:
            return None

        bet_usd = self.current_bankroll * bet_pct

        # Minimum bet check ($0.10 minimum, we're not here to waste gas)
        if bet_usd < 0.10:
            return None

        # Determine aggression level
        if bet_pct > 0.20:
            aggression = "full_degen"
        elif bet_pct > 0.10:
            aggression = "aggressive"
        else:
            aggression = "calculated"

        # Calculate stop loss
        stop_loss = self._calculate_stop_loss(opp)

        # Expected payout
        expected_payout = bet_usd * odds * win_prob

        rationale = self._generate_rationale(opp, win_prob, edge, bet_pct)

        return BetDecision(
            opportunity=opp,
            bet_size_pct=bet_pct,
            bet_size_usd=bet_usd,
            rationale=rationale,
            aggression_level=aggression,
            expected_payout=expected_payout,
            stop_loss_price=stop_loss,
        )

    def _estimate_win_probability(self, opp: Opportunity) -> float:
        """
        Estimate our probability of winning this bet.

        Uses a combination of:
        - Base confidence from the opportunity
        - Momentum bonus
        - Volume confirmation
        - Our inherent optimism bias
        """
        base_prob = opp.confidence

        # Momentum bonus: trending = more likely to continue (in our minds)
        momentum_bonus = opp.momentum_score * 0.1

        # Volume confirmation: high volume = more conviction
        volume_bonus = min(opp.volume_24h / 100000, 0.05) if opp.volume_24h > 10000 else 0

        # Optimism bias: we always think we're slightly better than we are
        optimism_bias = 0.05 if self.config.optimism_level == "DELUSIONAL" else 0.02

        prob = base_prob + momentum_bonus + volume_bonus + optimism_bias

        return max(min(prob, 0.95), 0.05)  # Clamp between 5% and 95%

    def _calculate_stop_loss(self, opp: Opportunity) -> Optional[float]:
        """
        Stop loss calculation.

        We DO have stop losses because we're delusional, not reckless.
        (Okay, maybe a little reckless.)
        """
        stop_pct = self.config.trading.stop_loss_pct

        # Widen stop loss on high-conviction plays
        if opp.confidence > 0.8:
            stop_pct *= 1.5  # Give winners room to breathe

        if opp.bet_type in (BetType.POLYMARKET_YES, BetType.POLYMARKET_NO):
            return max(opp.current_price * (1 - stop_pct), 0.01)
        else:
            return opp.current_price * (1 - stop_pct)

    def rank_opportunities(self, opportunities: list[Opportunity]) -> list[BetDecision]:
        """
        Rank all opportunities and return sorted bet decisions.

        Priority:
        1. High edge + high confidence = chef's kiss
        2. Momentum plays with volume confirmation
        3. Time-sensitive opportunities (expiring markets)
        4. Contrarian plays (low confidence but massive payoff)
        """
        decisions = []
        for opp in opportunities:
            decision = self.evaluate_opportunity(opp)
            if decision:
                decisions.append(decision)

        # Sort by expected value, but weight time-sensitive ones higher
        decisions.sort(
            key=lambda d: (
                d.expected_payout
                * (1 + d.opportunity.time_sensitivity)
                * (1.2 if d.aggression_level == "full_degen" else 1.0)
            ),
            reverse=True,
        )

        return decisions

    def record_result(self, won: bool, pnl: float):
        """Record a bet result and update streaks."""
        self.total_bets += 1
        self.current_bankroll += pnl

        if self.current_bankroll > self.peak_bankroll:
            self.peak_bankroll = self.current_bankroll
            self.doublings_achieved = int(
                math.log2(self.peak_bankroll / self.config.trading.starting_capital_usd)
            ) if self.peak_bankroll > self.config.trading.starting_capital_usd else 0

        if won:
            self.winning_bets += 1
            if self.current_streak_type == "win":
                self.consecutive_wins += 1
            else:
                self.current_streak_type = "win"
                self.consecutive_wins = 1
                self.consecutive_losses = 0
        else:
            if self.current_streak_type == "loss":
                self.consecutive_losses += 1
            else:
                self.current_streak_type = "loss"
                self.consecutive_losses = 1
                self.consecutive_wins = 0

        self.bet_history.append({
            "won": won,
            "pnl": pnl,
            "bankroll_after": self.current_bankroll,
        })

    def should_cut_losses(self, opp: Opportunity) -> bool:
        """
        The hardest decision: when to fold.

        We're optimistic, but we're not stupid (debatable).
        Cut when:
        - Position is down > stop_loss_pct AND momentum is against us
        - Market conditions have fundamentally changed
        - We've lost 50% of peak (drawdown limit)
        """
        # Drawdown check
        if self.peak_bankroll > 0:
            drawdown = (self.peak_bankroll - self.current_bankroll) / self.peak_bankroll
            if drawdown > 0.50:
                return True

        # 5 consecutive losses - take a breather, reassess
        if self.consecutive_losses >= 5:
            return True

        return False

    def _generate_rationale(self, opp: Opportunity, win_prob: float,
                            edge: float, bet_pct: float) -> str:
        """Generate a human-readable rationale for the bet."""
        rationales = {
            "full_degen": [
                f"SENDING IT. {edge:.1%} edge on {opp.market_name}. "
                f"Win prob {win_prob:.1%}. Size: {bet_pct:.1%} of bankroll. LFG.",
                f"This is THE play. {opp.market_name} is mispriced by {edge:.1%}. "
                f"Going {bet_pct:.1%} deep. $2M incoming.",
            ],
            "aggressive": [
                f"Strong conviction on {opp.market_name}. {edge:.1%} edge, "
                f"{win_prob:.1%} win rate. Sizing {bet_pct:.1%}.",
                f"Momentum + edge on {opp.market_name}. Taking a {bet_pct:.1%} position.",
            ],
            "calculated": [
                f"Measured entry on {opp.market_name}. Edge: {edge:.1%}, "
                f"Kelly says {bet_pct:.1%}. Disciplined degen.",
                f"Small but smart bet on {opp.market_name}. {edge:.1%} edge detected.",
            ],
        }

        aggression = "full_degen" if bet_pct > 0.20 else "aggressive" if bet_pct > 0.10 else "calculated"
        options = rationales.get(aggression, rationales["calculated"])
        return random.choice(options)

    def get_status_report(self) -> dict:
        """Get current status of the gambling engine."""
        return {
            "bankroll": f"${self.current_bankroll:.2f}",
            "target": f"${self.config.trading.moonshot_target_usd:,.0f}",
            "progress_to_moon": f"{self.progress_to_moon:.2f}%",
            "doublings_achieved": self.doublings_achieved,
            "doublings_needed": self.config.doublings_needed,
            "total_bets": self.total_bets,
            "win_rate": f"{self.win_rate:.1%}",
            "streak": f"{'W' if self.current_streak_type == 'win' else 'L'}{max(self.consecutive_wins, self.consecutive_losses)}" if self.current_streak_type else "N/A",
            "peak_bankroll": f"${self.peak_bankroll:.2f}",
            "optimism_level": self.config.optimism_level,
            "vibe": "IMMACULATE" if self.current_bankroll > self.config.trading.starting_capital_usd else "REBUILDING",
        }
