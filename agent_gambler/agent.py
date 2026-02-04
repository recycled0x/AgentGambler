"""
The Agent - The autonomous $2 to $2M machine.

Main loop:
1. Scan markets (Polymarket + Base DEX)
2. Evaluate opportunities through Gambler's Logic
3. Execute best bets
4. Monitor positions
5. Repeat until $2M or glory
"""

import time
import signal
import sys
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.text import Text

from agent_gambler.config import AgentConfig
from agent_gambler.strategies.gamblers_logic import GamblersLogic
from agent_gambler.markets.polymarket import PolymarketClient
from agent_gambler.markets.base_dex import BaseDEXClient
from agent_gambler.trading.portfolio import PortfolioManager
from agent_gambler.trading.executor import TradeExecutor

console = Console()


class AgentGambler:
    """
    The autonomous trading agent.

    Born with $2. Destined for $2M.
    Armed with Kelly Criterion, momentum detection, and pure delusion.
    """

    BANNER = r"""
     _                    _    ____                 _     _
    / \   __ _  ___ _ __ | |_ / ___| __ _ _ __ ___ | |__ | | ___ _ __
   / _ \ / _` |/ _ \ '_ \| __| |  _ / _` | '_ ` _ \| '_ \| |/ _ \ '__|
  / ___ \ (_| |  __/ | | | |_| |_| | (_| | | | | | | |_) | |  __/ |
 /_/   \_\__, |\___|_| |_|\__|\____|\__,_|_| |_| |_|_.__/|_|\___|_|
         |___/

              $2 -> $2,000,000 | Trust the Process
    """

    def __init__(self, config: AgentConfig, live_mode: bool = False):
        self.config = config
        self.live_mode = live_mode
        self.running = False

        # Initialize components
        self.strategy = GamblersLogic(config)
        self.polymarket = PolymarketClient(config)
        self.base_dex = BaseDEXClient(config)
        self.portfolio = PortfolioManager(config)
        self.executor = TradeExecutor(config, self.portfolio, live_mode)

        # Scan interval (seconds)
        self.scan_interval = 30
        self.cycle_count = 0

    def start(self):
        """Start the agent. Here we go."""
        console.print(self.BANNER, style="bold cyan")
        console.print()

        mode_text = "[bold red]LIVE MODE[/bold red]" if self.live_mode else "[bold yellow]SIMULATION MODE[/bold yellow]"
        console.print(Panel(
            f"Mode: {mode_text}\n"
            f"Starting Capital: [green]${self.config.trading.starting_capital_usd:.2f}[/green]\n"
            f"Target: [bold green]${self.config.trading.moonshot_target_usd:,.0f}[/bold green]\n"
            f"Doublings Needed: [cyan]{self.config.doublings_needed}[/cyan]\n"
            f"Optimism Level: [bold magenta]{self.config.optimism_level}[/bold magenta]\n"
            f"Kelly Fraction: [yellow]{self.config.trading.kelly_fraction}[/yellow]\n"
            f"Max Bet Size: [yellow]{self.config.trading.max_single_bet_pct:.0%}[/yellow] of bankroll",
            title="[bold]AgentGambler v0.1.0[/bold]",
            subtitle="[dim]Only ~20 doublings to go[/dim]",
        ))

        # Try to load previous state
        self.portfolio.load_state()

        # Signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown_handler)
        signal.signal(signal.SIGTERM, self._shutdown_handler)

        self.running = True
        console.print("\n[bold green]Agent started. Scanning for opportunities...[/bold green]\n")

        self._main_loop()

    def _main_loop(self):
        """The main trading loop. Where fortunes are made."""
        while self.running:
            self.cycle_count += 1
            cycle_start = time.time()

            try:
                console.rule(f"[bold cyan]Cycle #{self.cycle_count}[/bold cyan] - {datetime.now().strftime('%H:%M:%S')}")

                # Step 1: Scan for opportunities
                opportunities = self._scan_all_markets()

                if opportunities:
                    console.print(f"[green]Found {len(opportunities)} opportunities[/green]")

                    # Step 2: Evaluate through Gambler's Logic
                    decisions = self.strategy.rank_opportunities(opportunities)

                    if decisions:
                        # Step 3: Execute top decisions
                        self._execute_decisions(decisions)

                else:
                    console.print("[dim]No opportunities this cycle. Markets are quiet.[/dim]")

                # Step 4: Monitor existing positions
                self._monitor_positions()

                # Step 5: Display status
                self._display_status()

                # Save state
                self.portfolio.save_state()

                # Check if we've made it
                if self.portfolio.total_portfolio_value >= self.config.trading.moonshot_target_usd:
                    self._celebrate_victory()
                    break

                # Check if we're busted
                if self.portfolio.total_portfolio_value < 0.01:
                    console.print("\n[bold red]REKT. Bankroll depleted.[/bold red]")
                    console.print("[dim]But hey, it was only $2. Time to reload.[/dim]")
                    break

                # Wait for next cycle
                elapsed = time.time() - cycle_start
                wait_time = max(self.scan_interval - elapsed, 5)
                console.print(f"\n[dim]Next scan in {wait_time:.0f}s...[/dim]\n")
                time.sleep(wait_time)

            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error in cycle: {e}[/red]")
                time.sleep(10)

        self._shutdown()

    def _scan_all_markets(self):
        """Scan all market sources for opportunities."""
        all_opportunities = []

        # Scan Polymarket
        console.print("[cyan]Scanning Polymarket...[/cyan]")
        try:
            poly_opps = self.polymarket.scan_for_opportunities()
            all_opportunities.extend(poly_opps)
            console.print(f"  Found {len(poly_opps)} Polymarket opportunities")
        except Exception as e:
            console.print(f"  [red]Polymarket scan error: {e}[/red]")

        # Scan Base DEX
        console.print("[cyan]Scanning Base DEX...[/cyan]")
        try:
            dex_opps = self.base_dex.scan_for_opportunities()
            all_opportunities.extend(dex_opps)
            console.print(f"  Found {len(dex_opps)} Base DEX opportunities")
        except Exception as e:
            console.print(f"  [red]Base DEX scan error: {e}[/red]")

        return all_opportunities

    def _execute_decisions(self, decisions: list):
        """Execute the top bet decisions."""
        max_concurrent = 3  # Max simultaneous positions
        open_count = len([p for p in self.portfolio.positions.values() if p.status == "open"])

        for decision in decisions[:max_concurrent - open_count]:
            # Check if we have enough balance
            if decision.bet_size_usd > self.portfolio.available_balance:
                console.print(f"[yellow]Skipping {decision.opportunity.market_name}: "
                            f"insufficient balance[/yellow]")
                continue

            # Check if we should cut losses first
            if self.strategy.should_cut_losses(decision.opportunity):
                console.print("[yellow]Loss limit reached. Pausing new entries.[/yellow]")
                break

            console.print(f"\n[bold green]PLACING BET:[/bold green]")
            console.print(f"  Market: {decision.opportunity.market_name}")
            console.print(f"  Size: ${decision.bet_size_usd:.2f} ({decision.bet_size_pct:.1%})")
            console.print(f"  Aggression: {decision.aggression_level}")
            console.print(f"  Rationale: {decision.rationale}")

            result = self.executor.execute_bet(decision)

            if result.success:
                console.print(f"  [green]EXECUTED @ ${result.executed_price:.4f} "
                            f"(fees: ${result.fees:.4f}) [{result.mode}][/green]")
                self.strategy.record_result(True, 0)  # Will track actual P&L on close
            else:
                console.print(f"  [red]FAILED: {result.error}[/red]")

    def _monitor_positions(self):
        """Monitor open positions for stop losses and take profits."""
        stopped = self.portfolio.check_stop_losses()
        for pid in stopped:
            pos = self.portfolio.positions.get(pid)
            if pos:
                console.print(f"[red]STOP LOSS triggered on {pos.market_name}[/red]")
                self.executor.close_position(pid, pos.current_price, "stop_loss")
                self.strategy.record_result(False, -pos.size_usd * self.config.trading.stop_loss_pct)

    def _display_status(self):
        """Display current portfolio and strategy status."""
        # Portfolio table
        summary = self.portfolio.get_portfolio_summary()
        strategy_status = self.strategy.get_status_report()

        table = Table(title="Portfolio Status", show_header=True)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Value", summary["total_value"])
        table.add_row("Cash", summary["cash_balance"])
        table.add_row("Return", summary["total_return"])
        table.add_row("Open Positions", str(summary["open_positions"]))
        table.add_row("Win Rate", summary["win_rate"])
        table.add_row("Streak", strategy_status["streak"])
        table.add_row("Moon Progress", strategy_status["progress_to_moon"])
        table.add_row("Vibe", strategy_status["vibe"])

        console.print(table)

        # Open positions
        open_positions = [p for p in self.portfolio.positions.values() if p.status == "open"]
        if open_positions:
            pos_table = Table(title="Open Positions", show_header=True)
            pos_table.add_column("Market")
            pos_table.add_column("Side")
            pos_table.add_column("Size")
            pos_table.add_column("Entry")
            pos_table.add_column("Current")
            pos_table.add_column("P&L")

            for pos in open_positions:
                pnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
                pos_table.add_row(
                    pos.market_name[:40],
                    pos.side,
                    f"${pos.size_usd:.2f}",
                    f"${pos.entry_price:.4f}",
                    f"${pos.current_price:.4f}",
                    f"[{pnl_style}]${pos.unrealized_pnl:+.2f} ({pos.unrealized_pnl_pct:+.1f}%)[/{pnl_style}]",
                )

            console.print(pos_table)

    def _celebrate_victory(self):
        """WE MADE IT."""
        console.print("\n\n")
        console.print("[bold green]" + "=" * 60 + "[/bold green]")
        console.print("[bold green]   $2 TO $2,000,000 - MISSION ACCOMPLISHED   [/bold green]")
        console.print("[bold green]" + "=" * 60 + "[/bold green]")
        console.print(f"\nFinal Portfolio Value: [bold green]${self.portfolio.total_portfolio_value:,.2f}[/bold green]")
        console.print(f"Total Trades: {len(self.portfolio.trade_history)}")
        console.print(f"Win Rate: {self.portfolio.win_rate:.1%}")
        console.print(f"Profit Factor: {self.portfolio.profit_factor:.2f}")
        console.print("\n[bold]The delusional optimism was justified all along.[/bold]\n")

    def _shutdown_handler(self, signum, frame):
        """Handle shutdown gracefully."""
        console.print("\n[yellow]Shutdown signal received...[/yellow]")
        self.running = False

    def _shutdown(self):
        """Clean shutdown."""
        console.print("\n[yellow]Shutting down AgentGambler...[/yellow]")
        self.portfolio.save_state()
        console.print("[green]State saved. See you next time.[/green]")
        console.print(f"[dim]Final bankroll: ${self.portfolio.total_portfolio_value:.2f}[/dim]")
        console.print("[dim]Remember: it's not gambling if you have an edge.[/dim]")
