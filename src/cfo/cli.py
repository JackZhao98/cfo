"""Top-level typer app."""
import typer

from cfo import __version__

app = typer.Typer(
    name="cfo",
    help="Chief Financial Officer — personal finance CLI for Robinhood users.",
    no_args_is_help=True,
)


@app.callback()
def _main():
    """Chief Financial Officer — personal finance CLI for Robinhood users."""
    # Presence of this callback forces typer to require a subcommand
    # instead of treating a single @app.command as the root command.


@app.command()
def version():
    """Print cfo version."""
    typer.echo(f"cfo {__version__}")


from cfo.commands.portfolio import portfolio_app  # noqa: E402

app.add_typer(portfolio_app, name="portfolio")

from cfo.commands.init import init as init_cmd  # noqa: E402

app.command("init", help="Run the 15-question onboarding questionnaire.")(init_cmd)

from cfo.commands.tradebook import tradebook_app  # noqa: E402

app.add_typer(tradebook_app, name="tradebook")

from cfo.commands.strategy import strategy_app  # noqa: E402

app.add_typer(strategy_app, name="strategy")
