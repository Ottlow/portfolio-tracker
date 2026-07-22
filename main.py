"""
main.py — Portfolio Tracker (refresh 10 s, animations, P&L réel).

Usage :
    python main.py
    python main.py --file mon_ptf.csv --refresh 10
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.live import Live

from display import build_dashboard, REFRESH_TOTAL
from fetcher import DataFetcher
from metrics import (
    compute_positions,
    compute_portfolio_metrics,
    compute_real_pnl,
    compute_extended_metrics,
    compute_markowitz_optimization,
)

logging.basicConfig(
    filename="tracker.log",
    level=logging.WARNING,
    format="%(asctime)s  %(levelname)s  %(name)s — %(message)s",
)

console = Console()
REFRESH_INTERVAL = 5    # secondes


def load_portfolio(filepath: str) -> pd.DataFrame:
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {filepath}")
    df = pd.read_csv(path)
    missing = {"ticker", "quantity", "avg_cost"} - set(df.columns)
    if missing:
        raise ValueError(f"Colonnes manquantes : {missing}")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["avg_cost"] = pd.to_numeric(df["avg_cost"], errors="coerce")
    invalid = df[["quantity", "avg_cost"]].isna().any(axis=1)
    if invalid.any():
        raise ValueError(f"Valeurs invalides pour : {df[invalid]['ticker'].tolist()}")
    return df.reset_index(drop=True)


def run(portfolio_file: str, refresh_interval: int) -> None:
    try:
        portfolio_raw = load_portfolio(portfolio_file)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Erreur :[/red] {exc}")
        sys.exit(1)

    tickers = list(portfolio_raw["ticker"])
    console.print(
        f"[bold cyan]📈 Portfolio Tracker[/bold cyan] — "
        f"{len(tickers)} titres · refresh [yellow]{refresh_interval}s[/yellow] · [dim]Ctrl+C pour quitter[/dim]"
    )

    fetcher = DataFetcher(tickers)

    positions_df = None
    metrics      = None
    real_pnl_d   = None
    ext_metrics  = None
    market_ctx   = None
    infl_by_ccy  = None
    markowitz    = None
    last_update  = None
    flash        = 0
    loading      = True

    def fetch_and_compute() -> None:
        nonlocal positions_df, metrics, real_pnl_d, ext_metrics, market_ctx, infl_by_ccy, markowitz, last_update, flash, loading
        loading = True
        try:
            market_data  = fetcher.fetch_all()
            positions_df = compute_positions(portfolio_raw, market_data)
            metrics      = compute_portfolio_metrics(positions_df, market_data)
            real_pnl_d   = compute_real_pnl(positions_df, market_data.fx_rates,
                                             live_inflation=market_data.inflation_by_currency)
            ext_metrics  = compute_extended_metrics(positions_df, market_data, market_data.fx_rates)
            markowitz    = compute_markowitz_optimization(positions_df, market_data, market_data.fx_rates)
            market_ctx   = market_data.market_context
            infl_by_ccy  = market_data.inflation_by_currency
            last_update  = market_data.timestamp
            flash        = 3
        except Exception as exc:
            logging.error("Erreur fetch_and_compute : %s", exc, exc_info=True)
        finally:
            loading = False

    # Premier chargement
    fetch_and_compute()

    with Live(
        build_dashboard(positions_df, metrics, real_pnl_d, ext_metrics,
                        last_update, refresh_interval, flash, loading, market_ctx,
                        infl_by_ccy, markowitz),
        refresh_per_second=4,
        console=console,
        screen=True,
    ) as live:
        last_fetch_ts = time.monotonic()

        while True:
            try:
                now     = time.monotonic()
                elapsed = now - last_fetch_ts

                if elapsed >= refresh_interval:
                    fetch_and_compute()
                    last_fetch_ts = time.monotonic()

                if flash > 0:
                    flash -= 1

                time_to_next = max(0, int(refresh_interval - (time.monotonic() - last_fetch_ts)))
                live.update(
                    build_dashboard(positions_df, metrics, real_pnl_d, ext_metrics,
                                    last_update, time_to_next, flash, loading, market_ctx,
                                    infl_by_ccy, markowitz)
                )
                time.sleep(1)

            except KeyboardInterrupt:
                console.print("\n[yellow]Au revoir ![/yellow]")
                break


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Portfolio Tracker")
    p.add_argument("--file",    "-f", default="portfolio.csv")
    p.add_argument("--refresh", "-r", type=int, default=REFRESH_INTERVAL)
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(portfolio_file=args.file, refresh_interval=args.refresh)
