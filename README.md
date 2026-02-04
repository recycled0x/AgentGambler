# AgentGambler

**$2 to $2,000,000** - An autonomous trading agent powered by optimistic delusion.

```
     _                    _    ____                 _     _
    / \   __ _  ___ _ __ | |_ / ___| __ _ _ __ ___ | |__ | | ___ _ __
   / _ \ / _` |/ _ \ '_ \| __| |  _ / _` | '_ ` _ \| '_ \| |/ _ \ '__|
  / ___ \ (_| |  __/ | | | |_| |_| | (_| | | | | | | |_) | |  __/ |
 /_/   \_\__, |\___|_| |_|\__|\____|\__,_|_| |_| |_|_.__/|_|\___|_|
         |___/
```

## The Mission

Turn **$2 in ETH** into **$2,000,000** using autonomous trading on:
- **Polymarket** - Prediction market bets
- **Base Chain DEXes** - Token momentum trades, dip buys, and liquidity sniping

Only ~20 doublings. Easy.

## Strategy

The agent uses **Gambler's Logic** - a hybrid strategy combining:

1. **Modified Kelly Criterion** - Optimal bet sizing, but more aggressive because we believe
2. **Martingale Recovery** - Controlled position scaling on losses (they can't last forever)
3. **Momentum Chasing** - Ride winners, they tend to keep winning
4. **Contrarian Sniping** - Buy when others panic
5. **Compound Everything** - Never take profits early. Let it ride to $2M

### Risk Management
- Stop losses on every position (we're delusional, not reckless)
- Max 25% of bankroll on a single bet
- Drawdown limits at 50%
- Kelly fraction at 0.5x for some sanity

## Quick Start

```bash
# Clone
git clone https://github.com/recycled0x/AgentGambler.git
cd AgentGambler

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your wallet details

# Run in simulation mode (no real money)
python -m agent_gambler.cli run

# Run a single market scan
python -m agent_gambler.cli scan

# Check status
python -m agent_gambler.cli status

# LIVE MODE (real money - confirm when prompted)
python -m agent_gambler.cli run-live
```

## Architecture

```
agent_gambler/
  agent.py           - Main autonomous agent loop
  cli.py             - CLI entry point
  config.py          - Configuration management
  strategies/
    gamblers_logic.py - The brain: Kelly + Martingale + Momentum
  markets/
    polymarket.py     - Polymarket CLOB API integration
    base_dex.py       - Base chain DEX trading (Uniswap V3 / Aerodrome)
  trading/
    portfolio.py      - Position & P&L tracking
    executor.py       - Trade execution (simulation + live)
```

## Configuration

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `STARTING_CAPITAL_USD` | 2.00 | Starting bankroll |
| `MOONSHOT_TARGET_USD` | 2000000.00 | The dream |
| `MAX_SINGLE_BET_PCT` | 0.25 | Max bet as % of bankroll |
| `KELLY_FRACTION` | 0.5 | Kelly criterion fraction |
| `STOP_LOSS_PCT` | 0.15 | Stop loss percentage |
| `OPTIMISM_LEVEL` | DELUSIONAL | Agent personality |

## Disclaimer

This is an experimental trading agent. It will very likely lose money. The $2M target is aspirational (delusional). Only risk what you can afford to lose. This is not financial advice. We are not financial advisors. We are gamblers with a Python script.

But also... what if it works?
