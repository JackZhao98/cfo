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


# Subcommand groups added in later tasks (portfolio, init, migrate, ...).
