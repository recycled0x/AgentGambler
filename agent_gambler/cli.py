"""
CLI Entry Point for AgentGambler.

Commands:
  run       - Start the agent (simulation mode)
  run-live  - Start the agent (live mode - real money)
  status    - Show current portfolio status
  scan      - Run a single market scan
  config    - Show current configuration
"""

import click
from rich.console import Console
from rich.panel import Panel

from agent_gambler.config import AgentConfig
from agent_gambler.agent import AgentGambler

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="AgentGambler")
def cli():
    """AgentGambler - $2 to $2M autonomous trading agent."""
    pass


@cli.command()
@click.option("--scan-interval", default=30, help="Seconds between market scans")
def run(scan_interval):
    """Start the agent in SIMULATION mode. No real money at risk."""
    config = AgentConfig()
    agent = AgentGambler(config, live_mode=False)
    agent.scan_interval = scan_interval
    agent.start()


@cli.command("run-live")
@click.option("--scan-interval", default=30, help="Seconds between market scans")
@click.confirmation_option(
    prompt="This will trade with REAL MONEY. Are you sure?"
)
def run_live(scan_interval):
    """Start the agent in LIVE mode. Real money. Real gains. Real risk."""
    config = AgentConfig()

    if not config.wallet.private_key:
        console.print("[red]No PRIVATE_KEY configured in .env file.[/red]")
        console.print("Set up your .env file first. See .env.example")
        return

    console.print(Panel(
        "[bold red]LIVE MODE ACTIVATED[/bold red]\n\n"
        "This agent will execute REAL trades with REAL money.\n"
        "Starting with real ETH from your wallet.\n\n"
        "[yellow]Only risk what you can afford to lose.[/yellow]\n"
        "[dim](But we're going to $2M so it's fine)[/dim]",
        title="WARNING",
    ))

    agent = AgentGambler(config, live_mode=True)
    agent.scan_interval = scan_interval
    agent.start()


@cli.command()
def scan():
    """Run a single market scan and show opportunities."""
    config = AgentConfig()
    agent = AgentGambler(config, live_mode=False)

    console.print("[cyan]Running single market scan...[/cyan]\n")
    opportunities = agent._scan_all_markets()

    if not opportunities:
        console.print("[yellow]No opportunities found.[/yellow]")
        return

    from rich.table import Table
    table = Table(title=f"Found {len(opportunities)} Opportunities")
    table.add_column("Market", style="cyan")
    table.add_column("Type")
    table.add_column("Price")
    table.add_column("Fair Value")
    table.add_column("Edge", style="green")
    table.add_column("Confidence")
    table.add_column("Volume 24h")

    for opp in opportunities[:20]:
        table.add_row(
            opp.market_name[:50],
            opp.bet_type.value,
            f"${opp.current_price:.4f}",
            f"${opp.estimated_fair_value:.4f}",
            f"{opp.perceived_edge:.1%}",
            f"{opp.confidence:.1%}",
            f"${opp.volume_24h:,.0f}",
        )

    console.print(table)

    # Show what the strategy would do
    decisions = agent.strategy.rank_opportunities(opportunities)
    if decisions:
        console.print(f"\n[green]Strategy would place {len(decisions)} bets:[/green]")
        for d in decisions[:5]:
            console.print(f"  - {d.opportunity.market_name}: ${d.bet_size_usd:.2f} ({d.aggression_level})")
            console.print(f"    {d.rationale}")


@cli.command()
def status():
    """Show current portfolio status."""
    config = AgentConfig()
    from agent_gambler.trading.portfolio import PortfolioManager

    portfolio = PortfolioManager(config)
    portfolio.load_state()

    summary = portfolio.get_portfolio_summary()

    console.print(Panel(
        f"Total Value: [bold green]{summary['total_value']}[/bold green]\n"
        f"Cash: {summary['cash_balance']}\n"
        f"Exposure: {summary['total_exposure']}\n"
        f"Return: {summary['total_return']}\n"
        f"Win Rate: {summary['win_rate']}\n"
        f"Total Trades: {summary['total_trades']}\n"
        f"Open Positions: {summary['open_positions']}\n"
        f"Target: {summary['target']}\n"
        f"Progress: {summary['progress']}",
        title="[bold]Portfolio Status[/bold]",
    ))


@cli.command()
def config():
    """Show current agent configuration."""
    cfg = AgentConfig()

    console.print(Panel(
        f"Optimism Level: [bold magenta]{cfg.optimism_level}[/bold magenta]\n"
        f"Starting Capital: ${cfg.trading.starting_capital_usd:.2f}\n"
        f"Target: ${cfg.trading.moonshot_target_usd:,.0f}\n"
        f"Doublings Needed: {cfg.doublings_needed}\n"
        f"Kelly Fraction: {cfg.trading.kelly_fraction}\n"
        f"Max Bet Size: {cfg.trading.max_single_bet_pct:.0%}\n"
        f"Stop Loss: {cfg.trading.stop_loss_pct:.0%}\n"
        f"Min Edge: {cfg.trading.min_edge_threshold:.0%}\n"
        f"Compound Wins: {cfg.trading.compound_wins}\n"
        f"Base RPC: {cfg.rpc.base_rpc_url}\n"
        f"Wallet: {'Configured' if cfg.wallet.private_key else 'Not set'}",
        title="[bold]Agent Configuration[/bold]",
    ))


def main():
    cli()


if __name__ == "__main__":
    main()
