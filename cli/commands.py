"""CLI commands for tradebot."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from tradebot import __version__, __logo__

app = typer.Typer(
    name="tradebot",
    help=f"{__logo__} tradebot - Automated Crypto Trading Bot",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} tradebot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """tradebot - Automated Crypto Trading Bot."""
    pass


# ============================================================================
# Setup / Init
# ============================================================================


@app.command()
def init():
    """Initialize tradebot configuration and trading workspace."""
    from tradebot.config.loader import get_config_path, save_config
    from tradebot.config.schema import Config
    from tradebot.utils.helpers import get_workspace_path

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not typer.confirm("Overwrite?"):
            raise typer.Exit()

    # Create default config
    config = Config()
    save_config(config)
    console.print(f"[green]✓[/green] Created config at {config_path}")

    # Create workspace
    workspace = get_workspace_path()
    console.print(f"[green]✓[/green] Created workspace at {workspace}")

    # Create default strategy files
    _create_workspace_templates(workspace)

    console.print(f"\n{__logo__} tradebot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your exchange API keys to [cyan]~/.tradebot/config.json[/cyan]")
    console.print("     Supported exchanges: Binance, Bybit, OKX, Kraken")
    console.print("  2. Run bot: [cyan]tradebot run --strategy scalping[/cyan]")
    console.print("\n[dim]Want Telegram alerts? See: https://github.com/user/tradebot#notifications[/dim]")


def _create_workspace_templates(workspace: Path):
    """Create default workspace strategy files."""
    templates = {
        "STRATEGY.md": """# Trading Strategy

Default strategy configuration for tradebot.

## Parameters

- Timeframe: 1h
- Max open positions: 3
- Risk per trade: 1%
- Stop-loss: 2%
- Take-profit: 4%

## Indicators

- RSI (14) - overbought/oversold detection
- EMA 50/200 - trend direction
- MACD - momentum confirmation
""",
        "PAIRS.md": """# Trading Pairs

Active trading pairs configuration.

## Spot

- BTC/USDT
- ETH/USDT
- SOL/USDT

## Filters

- Min 24h volume: $10,000,000
- Max spread: 0.1%
- Exclude: stablecoins, meme coins
""",
        "RISK.md": """# Risk Management

Risk management rules enforced by tradebot.

## Limits

- Daily loss limit: 3%
- Max drawdown: 10%
- Max leverage: 5x

## Emergency

- Auto-pause on daily loss limit breach
- Notify via Telegram on large drawdown
- Close all positions on critical error
""",
    }

    for filename, content in templates.items():
        file_path = workspace / filename
        if not file_path.exists():
            file_path.write_text(content)
            console.print(f"  [dim]Created {filename}[/dim]")

    # Create logs directory
    logs_dir = workspace / "logs"
    logs_dir.mkdir(exist_ok=True)
    trade_log = logs_dir / "trades.csv"
    if not trade_log.exists():
        trade_log.write_text("timestamp,pair,side,price,amount,pnl,strategy\n")
        console.print("  [dim]Created logs/trades.csv[/dim]")


# ============================================================================
# Bot Runner
# ============================================================================


@app.command()
def run(
    port: int = typer.Option(18790, "--port", "-p", help="API server port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the tradebot engine."""
    from tradebot.config.loader import load_config, get_data_dir
    from tradebot.bus.queue import MessageBus
    from tradebot.providers.exchange_provider import ExchangeProvider
    from tradebot.agent.loop import AgentLoop
    from tradebot.channels.manager import ChannelManager
    from tradebot.cron.service import CronService
    from tradebot.cron.types import CronJob
    from tradebot.heartbeat.service import HeartbeatService

    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{__logo__} Starting tradebot engine on port {port}...")

    config = load_config()

    # Create components
    bus = MessageBus()

    # Create exchange provider (supports Binance, Bybit, OKX, Kraken)
    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_paper = model.startswith("paper/")

    if not api_key and not is_paper:
        console.print("[red]Error: No exchange API key configured.[/red]")
        console.print("Set one in ~/.tradebot/config.json under exchanges.binance.apiKey")
        raise typer.Exit(1)

    provider = ExchangeProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )

    # Create cron service for scheduled trading tasks
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    # Create trading agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        max_iterations=config.agents.defaults.max_tool_iterations,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
    )

    # Set cron callback for scheduled strategies
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a scheduled trading job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from tradebot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    cron.on_job = on_cron_job

    # Create market heartbeat (monitors positions every 30m)
    async def on_heartbeat(prompt: str) -> str:
        """Execute market check through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True
    )

    # Create notification channel manager
    channels = ChannelManager(config, bus)

    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Notifications enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No notification channels enabled[/yellow]")

    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Scheduled strategies: {cron_status['jobs']} jobs")

    console.print(f"[green]✓[/green] Market monitor: every 30m")

    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down tradebot...")
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()

    asyncio.run(run())


# ============================================================================
# Analyze / Backtest Commands
# ============================================================================


@app.command()
def analyze(
    message: str = typer.Option(None, "--message", "-m", help="Analysis query or command"),
    session_id: str = typer.Option("cli:default", "--session", "-s", help="Session ID"),
):
    """Run market analysis or interact with the trading agent."""
    from tradebot.config.loader import load_config
    from tradebot.bus.queue import MessageBus
    from tradebot.providers.exchange_provider import ExchangeProvider
    from tradebot.agent.loop import AgentLoop

    config = load_config()

    api_key = config.get_api_key()
    api_base = config.get_api_base()
    model = config.agents.defaults.model
    is_paper = model.startswith("paper/")

    if not api_key and not is_paper:
        console.print("[red]Error: No exchange API key configured.[/red]")
        raise typer.Exit(1)

    bus = MessageBus()
    provider = ExchangeProvider(
        api_key=api_key,
        api_base=api_base,
        default_model=config.agents.defaults.model
    )

    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        brave_api_key=config.tools.web.search.api_key or None,
        exec_config=config.tools.exec,
        restrict_to_workspace=config.tools.restrict_to_workspace,
    )

    if message:
        # Single query mode
        async def run_once():
            response = await agent_loop.process_direct(message, session_id)
            console.print(f"\n{__logo__} {response}")

        asyncio.run(run_once())
    else:
        # Interactive trading terminal
        console.print(f"{__logo__} Trading terminal (Ctrl+C to exit)\n")

        async def run_interactive():
            while True:
                try:
                    user_input = console.input("[bold blue]tradebot>[/bold blue] ")
                    if not user_input.strip():
                        continue

                    response = await agent_loop.process_direct(user_input, session_id)
                    console.print(f"\n{__logo__} {response}\n")
                except KeyboardInterrupt:
                    console.print("\nExiting terminal.")
                    break

        asyncio.run(run_interactive())


# ============================================================================
# Notification Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage notification channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show notification channel status."""
    from tradebot.config.loader import load_config

    config = load_config()

    table = Table(title="Notification Channels")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        "✓" if wa.enabled else "✗",
        wa.bridge_url
    )

    dc = config.channels.discord
    table.add_row(
        "Discord",
        "✓" if dc.enabled else "✗",
        dc.gateway_url
    )

    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row(
        "Telegram",
        "✓" if tg.enabled else "✗",
        tg_config
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess

    # User's bridge location
    user_bridge = Path.home() / ".tradebot" / "bridge"

    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # tradebot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall tradebot")
        raise typer.Exit(1)

    console.print(f"{__logo__} Setting up notification bridge...")

    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    # Install and build
    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)

        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)

        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


@channels_app.command("login")
def channels_login():
    """Link Telegram/WhatsApp for trade alerts via QR code."""
    import subprocess

    bridge_dir = _get_bridge_dir()

    console.print(f"{__logo__} Starting notification bridge...")
    console.print("Scan the QR code to connect.\n")

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")


# ============================================================================
# Scheduled Strategy Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled trading strategies")
app.add_typer(cron_app, name="schedule")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled strategies"),
):
    """List scheduled trading strategies."""
    from tradebot.config.loader import get_data_dir
    from tradebot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    jobs = service.list_jobs(include_disabled=all)

    if not jobs:
        console.print("No scheduled strategies.")
        return

    table = Table(title="Scheduled Strategies")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    import time
    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = job.schedule.expr or ""
        else:
            sched = "one-time"

        # Format next run
        next_run = ""
        if job.state.next_run_at_ms:
            next_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.state.next_run_at_ms / 1000))
            next_run = next_time

        status = "[green]active[/green]" if job.enabled else "[dim]paused[/dim]"

        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Strategy name"),
    message: str = typer.Option(..., "--message", "-m", help="Strategy command or analysis prompt"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Send result to notification channel"),
    to: str = typer.Option(None, "--to", help="Recipient for alert delivery"),
    channel: str = typer.Option(None, "--channel", help="Channel for delivery (e.g. 'telegram', 'discord')"),
):
    """Add a scheduled trading strategy."""
    from tradebot.config.loader import get_data_dir
    from tradebot.cron.service import CronService
    from tradebot.cron.types import CronSchedule

    # Determine schedule type
    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr)
    elif at:
        import datetime
        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.add_job(
        name=name,
        schedule=schedule,
        message=message,
        deliver=deliver,
        to=to,
        channel=channel,
    )

    console.print(f"[green]✓[/green] Scheduled strategy '{job.name}' ({job.id})")


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Strategy ID to remove"),
):
    """Remove a scheduled strategy."""
    from tradebot.config.loader import get_data_dir
    from tradebot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed strategy {job_id}")
    else:
        console.print(f"[red]Strategy {job_id} not found[/red]")


@cron_app.command("toggle")
def cron_enable(
    job_id: str = typer.Argument(..., help="Strategy ID"),
    disable: bool = typer.Option(False, "--pause", help="Pause instead of activate"),
):
    """Activate or pause a scheduled strategy."""
    from tradebot.config.loader import get_data_dir
    from tradebot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "paused" if disable else "activated"
        console.print(f"[green]✓[/green] Strategy '{job.name}' {status}")
    else:
        console.print(f"[red]Strategy {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Strategy ID to execute"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if paused"),
):
    """Manually trigger a scheduled strategy."""
    from tradebot.config.loader import get_data_dir
    from tradebot.cron.service import CronService

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print(f"[green]✓[/green] Strategy executed")
    else:
        console.print(f"[red]Failed to run strategy {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show tradebot status and exchange connections."""
    from tradebot.config.loader import load_config, get_config_path

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} tradebot Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")

    if config_path.exists():
        console.print(f"Strategy model: {config.agents.defaults.model}")

        # Check exchange API keys
        has_binance = bool(config.providers.openrouter.api_key)
        has_bybit = bool(config.providers.anthropic.api_key)
        has_okx = bool(config.providers.openai.api_key)
        has_kraken = bool(config.providers.gemini.api_key)
        has_paper = bool(config.providers.vllm.api_base)

        console.print(f"Binance API: {'[green]✓[/green]' if has_binance else '[dim]not set[/dim]'}")
        console.print(f"Bybit API:   {'[green]✓[/green]' if has_bybit else '[dim]not set[/dim]'}")
        console.print(f"OKX API:     {'[green]✓[/green]' if has_okx else '[dim]not set[/dim]'}")
        console.print(f"Kraken API:  {'[green]✓[/green]' if has_kraken else '[dim]not set[/dim]'}")
        paper_status = f"[green]✓ {config.providers.vllm.api_base}[/green]" if has_paper else "[dim]not set[/dim]"
        console.print(f"Paper trade: {paper_status}")


if __name__ == "__main__":
    app()
