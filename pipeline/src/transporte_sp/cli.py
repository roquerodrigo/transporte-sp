"""``transporte-sp`` — one entry point for the whole pipeline."""

from __future__ import annotations

import logging

import typer

from transporte_sp.sources import REGISTRY

app = typer.Typer(
    add_completion=False,
    help="Build an auditable dataset of São Paulo's metropolitan mass transit.",
)


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v", help="debug logging")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname).1s %(name)s: %(message)s",
    )


SOURCE_ARGUMENT = typer.Argument(None, help="sources to fetch; default: all")


@app.command()
def fetch(source: list[str] = SOURCE_ARGUMENT) -> None:
    """Store a dated raw snapshot of each source under data/raw/."""
    wanted = source or list(REGISTRY)
    unknown = [name for name in wanted if name not in REGISTRY]
    if unknown:
        raise typer.BadParameter(f"unknown source(s): {', '.join(unknown)}")

    failures: list[str] = []
    for name in wanted:
        typer.echo(f"→ {name}")
        try:
            REGISTRY[name].fetch()
        except Exception as error:  # noqa: BLE001 - one flaky source must not stop the rest
            failures.append(f"{name}: {error}")
            typer.secho(f"  failed: {error}", fg=typer.colors.YELLOW)
    if failures:
        typer.secho(f"{len(failures)} source(s) failed", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def build() -> None:
    """Reconcile the latest snapshots and write data/dist/."""
    from transporte_sp import export, merge

    export.write_all(merge.build())


@app.command()
def pages() -> None:
    """Generate the site's content from data/dist/network.json."""
    import json

    from transporte_sp.config import settings
    from transporte_sp.export import pages as site
    from transporte_sp.model import Network

    path = settings.dist_dir / "network.json"
    if not path.exists():
        raise typer.BadParameter(f"{path} not found; run `transporte-sp build` first")
    site.write_all(Network(**json.loads(path.read_text())))


@app.command()
def validate() -> None:
    """Check the invariants of data/dist/network.json."""
    import json

    from transporte_sp import validate as checks
    from transporte_sp.config import settings
    from transporte_sp.model import Network

    path = settings.dist_dir / "network.json"
    if not path.exists():
        raise typer.BadParameter(f"{path} not found; run `transporte-sp build` first")
    if checks.report(checks.check(Network(**json.loads(path.read_text())))):
        raise typer.Exit(1)


@app.command()
def inspect(source: str = typer.Argument(..., help="source to summarise")) -> None:
    """Print what the latest snapshot of a source yields, without reconciling anything."""
    if source not in REGISTRY:
        raise typer.BadParameter(f"unknown source: {source}")
    module = REGISTRY[source]
    if hasattr(module, "lines"):
        for line in module.lines():
            typer.echo(f"  line {line.number or '-':>3}  {line.name[:60]:60}  {line.status}")
    if hasattr(module, "stations"):
        typer.echo(f"  {len(module.stations())} stations")


if __name__ == "__main__":
    app()
