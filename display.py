"""
display.py - Dashboard terminal Rich - layout compact & moderne.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
from rich import box
from rich.align import Align
from rich.columns import Columns
from rich.table import Table as _GridTable
from rich.console import Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# Caracteres Unicode
FULL  = "█"
LIGHT = "░"
UP    = "▲"
DOWN  = "▼"
DOT   = "•"

# -----------------------------------------------------------------------
# Utilitaires
# -----------------------------------------------------------------------

def _sign(v: float) -> str:
    return "+" if v > 0 else ""

def _col(v: float, reverse: bool = False) -> str:
    if math.isnan(v):
        return "dim"
    pos = "bright_green" if v > 0 else "bright_red" if v < 0 else "white"
    neg = "bright_red"   if v > 0 else "bright_green" if v < 0 else "white"
    return pos if not reverse else neg

def _fmt_pct(v: float, arrow: bool = True) -> str:
    if math.isnan(v):
        return " N/A "
    s = f"{_sign(v)}{v:.2f}%"
    return s + (f" {UP}" if v > 0 else f" {DOWN}" if v < 0 else "  ") if arrow else s

def _fmt_m(v: float, dec: int = 2) -> str:
    if math.isnan(v):
        return "N/A"
    return f"{_sign(v)}{v:,.{dec}f}"

def _fmt_f(v: float, dec: int = 2) -> str:
    if math.isnan(v):
        return "N/A"
    return f"{v:.{dec}f}"


# -----------------------------------------------------------------------
# Header anime
# -----------------------------------------------------------------------

REFRESH_TOTAL = 5

def _market_status():
    """Retourne statut ouvert/ferme des marches US et EU."""
    now_utc = datetime.now(timezone.utc)
    month   = now_utc.month
    us_off  = -4 if 3 <= month <= 11 else -5
    eu_off  = 2  if 3 <= month <= 10 else 1
    now_us  = now_utc + timedelta(hours=us_off)
    now_eu  = now_utc + timedelta(hours=eu_off)
    wd      = now_utc.weekday()
    us_open = wd < 5 and (9, 30) <= (now_us.hour, now_us.minute) < (16, 0)
    eu_open = wd < 5 and (9, 0)  <= (now_eu.hour, now_eu.minute) < (17, 30)
    return us_open, eu_open, now_us.strftime("%H:%M"), now_eu.strftime("%H:%M")


def _vix_label(vix: float) -> tuple[str, str]:
    """Couleur et label textuel du VIX."""
    if math.isnan(vix):          return "dim",          "N/A"
    if vix < 15:                 return "bright_green",  "Calme"
    if vix < 20:                 return "green",         "Normal"
    if vix < 30:                 return "yellow",        "Eleve"
    if vix < 40:                 return "bright_red",    "Stress"
    return "bold bright_red",   "Crise"


def _build_header(last_update, next_refresh: int, flash: int, loading: bool,
                  market_ctx: "Optional[dict]" = None):
    update_str = last_update.strftime("%H:%M:%S") if last_update else "--:--:--"
    date_str   = last_update.strftime("%d/%m/%Y") if last_update else datetime.now().strftime("%d/%m/%Y")

    bar_width = 12
    ratio     = next_refresh / REFRESH_TOTAL
    filled    = int(ratio * bar_width)
    bar_col   = "bright_green" if ratio > 0.6 else "yellow" if ratio > 0.3 else "bright_red"

    # Cote gauche
    title = Text()
    title.append("  PORTFOLIO TRACKER ", style="bold bright_white")
    title.append("by Axel Ottow", style="dim white")

    status = Text()
    status.append(f"  {date_str}  ", style="dim")
    status.append(update_str, style="cyan")
    if loading:
        status.append("  ⏳ chargement...", style="bold yellow")
    elif flash > 0:
        status.append("  ✔ actualise", style="bold bright_green")
    else:
        status.append("  [", style="dim")
        status.append(FULL * filled,                style=bar_col)
        status.append(LIGHT * (bar_width - filled), style="dim")
        status.append(f"]  {next_refresh}s", style=f"dim {bar_col}")

    # Cote droit : contexte marche
    if market_ctx:
        spx  = market_ctx.get("^GSPC", {})
        vix  = market_ctx.get("^VIX",  {})
        fx   = market_ctx.get("EURUSD", {})
        us_open, eu_open, us_t, eu_t = _market_status()

        spx_p   = spx.get("price", float("nan"))
        spx_c   = spx.get("change_pct", float("nan"))
        vix_p   = vix.get("price", float("nan"))
        eurusd  = fx.get("price",  float("nan"))

        spx_col = _col(spx_c) if not math.isnan(spx_c) else "white"
        spx_sgn = _sign(spx_c)
        vix_col, vix_lbl = _vix_label(vix_p)

        us_lbl = "OPEN" if us_open else "CLOSE"
        eu_lbl = "OPEN" if eu_open else "CLOSE"
        us_col = "bright_green" if us_open else "bright_red"
        eu_col = "bright_green" if eu_open else "bright_red"

        mkt1 = Text()
        mkt1.append("S&P500 ", style="dim")
        mkt1.append(f"{spx_p:,.0f}  ", style="bold white")
        mkt1.append(f"{spx_sgn}{spx_c:.2f}%", style=spx_col)
        mkt1.append("   VIX ", style="dim")
        mkt1.append(f"{vix_p:.1f}  ", style="bold white")
        mkt1.append(f"{vix_lbl}  ", style=vix_col)

        mkt2 = Text()
        mkt2.append("● ", style=us_col)
        mkt2.append(f"US {us_lbl} {us_t} ET   ", style="dim")
        mkt2.append("● ", style=eu_col)
        mkt2.append(f"EU {eu_lbl} {eu_t} CET  ", style="dim")

        grid = _GridTable.grid(expand=True, padding=(0, 0))
        grid.add_column(ratio=3)
        grid.add_column(ratio=2, justify="right")
        grid.add_row(title,  mkt1)
        grid.add_row(status, mkt2)
        return Group(grid, Rule(style="bright_blue"))
    else:
        grid = _GridTable.grid(expand=True, padding=(0, 0))
        grid.add_column()
        grid.add_row(title)
        grid.add_row(status)
        return Group(grid, Rule(style="bright_blue"))


# -----------------------------------------------------------------------
# Tableau des positions
# -----------------------------------------------------------------------


def _build_markets_table(market_ctx: dict, infl_by_ccy: Optional[dict] = None) -> Table:
    """Mini tableau devises + commodites + inflation par devise."""
    tbl = Table(
        box=box.SIMPLE,
        header_style="bold bright_cyan",
        show_header=True,
        padding=(0, 1),
        show_edge=False,
    )
    tbl.add_column("Actif",  style="dim",    no_wrap=True, min_width=9)
    tbl.add_column("Prix",   justify="right", style="bold white", no_wrap=True)
    tbl.add_column("Jour",   justify="right", no_wrap=True)

    def _add(label, sym, fmt=".4f", prefix=""):
        d = market_ctx.get(sym, {})
        p = d.get("price", float("nan"))
        c = d.get("change_pct", float("nan"))
        if math.isnan(p):
            return
        p_str = prefix + f"{p:{fmt}}"
        c_col = _col(c)
        c_str = f"{_sign(c)}{c:.2f}%" if not math.isnan(c) else "--"
        arr   = f" {UP}" if (not math.isnan(c) and c > 0) else f" {DOWN}" if (not math.isnan(c) and c < 0) else ""
        tbl.add_row(label, p_str, Text(c_str + arr, style=c_col))

    def _infl_row(label: str, ccy: str):
        """Affiche le taux d'inflation le plus recent pour une devise."""
        if not infl_by_ccy or ccy not in infl_by_ccy:
            return
        ccy_rates = infl_by_ccy[ccy]
        if not ccy_rates:
            return
        latest_yr = max(ccy_rates.keys())
        rate = ccy_rates[latest_yr]
        rate_pct = rate * 100
        col = "bright_red" if rate_pct > 3.0 else "yellow" if rate_pct > 2.0 else "bright_green"
        tbl.add_row(
            Text(f" {label}", style="dim"),
            Text(f"{rate_pct:.2f}%", style=col),
            Text(f"{latest_yr}", style="dim"),
        )

    # Section devises
    tbl.add_row(Text("DEVISES", style="bold bright_cyan"), "", "")
    _add("EUR/USD", "EURUSD", ".4f")
    _infl_row("CPI USD", "USD")
    _add("EUR/CHF", "EURCHF", ".4f")
    _infl_row("CPI CHF", "CHF")
    _add("EUR/CAD", "EURCAD", ".4f")
    _infl_row("CPI CAD", "CAD")
    # EUR inflation
    _infl_row("HICP EUR", "EUR")
    _add("Bitcoin",  "BTC-USD", ",.0f", "$")
    # Section commodites
    tbl.add_row("", "", "")
    tbl.add_row(Text("COMMODITES", style="bold bright_cyan"), "", "")
    _add("Or (oz)",   "GC=F", ",.1f", "$")
    _add("WTI Crude", "CL=F", ".2f",  "$")
    return tbl


def _build_positions_table(df: pd.DataFrame, flash: int,
                           markowitz: "Optional[dict]" = None) -> Table:
    total_pnl_eur  = df["pnl_eur"].sum()
    total_day_eur  = df["day_pnl_eur"].sum() if "day_pnl_eur" in df.columns else float("nan")

    # Index Markowitz par ticker
    mz_map: dict = {}
    if markowitz and markowitz.get("comparison"):
        for e in markowitz["comparison"]:
            mz_map[e["ticker"]] = e

    tbl = Table(
        box=box.SIMPLE,
        border_style="bright_blue",
        header_style="bold bright_cyan",
        show_footer=True,
        title=None,
        padding=(0, 1),
    )
    tbl.add_column("Ticker",  style="bold white",  no_wrap=True)
    tbl.add_column("Dev",     style="dim",          no_wrap=True)
    tbl.add_column("Qte",     justify="right",      style="dim")
    tbl.add_column("PA",      justify="right",      style="dim")
    tbl.add_column("Prix",    justify="right",      style="bold white")
    tbl.add_column("Jour %",  justify="right")
    tbl.add_column(
        "Jour EUR",
        justify="right",
        footer=Text(f"{_fmt_m(total_day_eur, 0)}", style=f"bold {_col(total_day_eur)}"),
    )
    tbl.add_column("Val. EUR", justify="right",     style="dim white")
    tbl.add_column("P&L %",    justify="right")
    tbl.add_column("P&L EUR",  justify="right")
    tbl.add_column("Poids",    justify="right",     style="dim")
    if mz_map:
        tbl.add_column("Opt %",   justify="right",  no_wrap=True)
        tbl.add_column("MkwSig",  justify="center", no_wrap=True)

    for _, r in df.iterrows():
        price = r.get("current_price", float("nan"))
        mz    = mz_map.get(r["ticker"])

        if math.isnan(price):
            base_row = [r["ticker"], "--", f"{r['quantity']:,.0f}",
                        f"{r['avg_cost']:.2f}", "[red]N/A[/red]",
                        "--", "--", "--", "--", "--", "--"]
            if mz_map:
                base_row += ["--", "--"]
            tbl.add_row(*base_row)
            continue

        dc      = r.get("day_change_pct", 0.0)
        dc_col  = _col(dc)
        pc_col  = _col(r["pnl"])
        pnl_eur = r["pnl_eur"]
        day_eur = r.get("day_pnl_eur", float("nan"))

        row = [
            r["ticker"],
            r.get("ticker_currency", "?"),
            f"{r['quantity']:,.0f}",
            f"{r['avg_cost']:.2f}",
            f"{price:,.2f}",
            Text(f"{_fmt_pct(dc)}", style=dc_col),
            Text(f"{_fmt_m(day_eur, 0)}", style=f"bold {_col(day_eur)}"),
            f"{r['market_value_eur']:,.0f}",
            Text(f"{_fmt_pct(r['pnl_pct'], False)}", style=pc_col),
            Text(f"{_fmt_m(pnl_eur, 0)}", style=f"bold {pc_col}"),
            f"{r['weight_eur']:.1f}%",
        ]

        if mz_map:
            if mz:
                sig = mz["signal"]
                sig_col = ("bright_green" if sig == "↑"
                           else "bright_red" if sig == "↓" else "dim")
                row += [
                    Text(f"{mz['optimal_pct']:.1f}%", style=sig_col),
                    Text(sig, style=f"bold {sig_col}"),
                ]
            else:
                row += [Text("--", style="dim"), Text("", style="dim")]

        tbl.add_row(*row)
    return tbl


# -----------------------------------------------------------------------
# Panneaux metriques
# -----------------------------------------------------------------------

def _panel_valorisation(metrics: dict, real_pnl: dict, em: Optional[dict], flash: int) -> Panel:
    hl    = "bold " if flash > 0 else ""
    total = real_pnl.get("total_eur", float("nan"))
    pnl_e = real_pnl.get("nominal_pnl_eur", float("nan"))
    pnl_p = real_pnl.get("nominal_pnl_pct", float("nan"))
    col   = _col(pnl_e)

    lines = [
        f"[dim]Valeur totale  :[/dim] [bold white]{total:>10,.0f} EUR[/bold white]",
        f"[dim]P&L achat      :[/dim] [{hl}{col}]{_fmt_m(pnl_e, 0):>10} EUR[/{hl}{col}]",
        f"[dim]Performance    :[/dim] [{hl}{col}]{_fmt_pct(pnl_p, False):>10}[/{hl}{col}]",
    ]

    if em:
        dc_e  = em.get("daily_pnl_eur", float("nan"))
        dc_p  = em.get("daily_pnl_pct", float("nan"))
        dc_col = _col(dc_e)
        ytd_col   = _col(em["ytd_pnl_eur"])
        alpha_col = _col(em["alpha_ytd"])
        yr = datetime.now().year
        lines += [
            f"[dim]               [/dim] [dim]──────────────[/dim]",
            f"[dim]P&L jour      :[/dim] [{hl}{dc_col}]{_fmt_m(dc_e, 0):>7} EUR  {_fmt_pct(dc_p, False):>7}[/{hl}{dc_col}]",
            f"[dim]               [/dim] [dim]──────────────[/dim]",
            f"[dim]YTD {yr}      :[/dim] [{hl}{ytd_col}]{_fmt_m(em['ytd_pnl_eur'], 0):>7} EUR  {_fmt_pct(em['ytd_pnl_pct'], False):>7}[/{hl}{ytd_col}]",
            f"[dim]S&P500 YTD    :[/dim] [white]{_fmt_pct(em['ytd_spx_pct'], False):>10}[/white]",
            f"[dim]Alpha S&P500  :[/dim] [{alpha_col}]{_fmt_pct(em['alpha_ytd'], False):>10}[/{alpha_col}]",
        ]

    return Panel("\n".join(lines), title="[bold bright_cyan]Valorisation[/bold bright_cyan]",
                 border_style="bright_blue", box=box.ROUNDED)


def _panel_risque(metrics: dict, em: "Optional[dict]") -> Panel:
    b     = metrics.get("beta",              float("nan"))
    vol   = metrics.get("volatility",        float("nan"))
    sh    = metrics.get("sharpe",            float("nan"))
    so    = metrics.get("sortino",           float("nan"))
    ir    = metrics.get("information_ratio", float("nan"))
    ca    = metrics.get("calmar",            float("nan"))
    tr    = metrics.get("treynor",           float("nan"))
    om    = metrics.get("omega",             float("nan"))
    ja    = metrics.get("jensen_alpha",      float("nan"))
    mdd   = metrics.get("max_drawdown",      float("nan"))
    var   = metrics.get("var_95",            float("nan"))
    cvar  = metrics.get("cvar_95",           float("nan"))
    skew  = metrics.get("skewness",          float("nan"))

    ja_col   = _col(ja)
    skew_col = ("bright_green" if (not math.isnan(skew) and skew > 0)
                else "bright_red" if (not math.isnan(skew) and skew < 0)
                else "white")

    wr_str = "--"
    if em:
        wr = em.get("win_rate", float("nan"))
        wr_str = f"{wr:.0f}%  ({em['winners']}/{em['total_pos']})"

    # Grille 2 colonnes : 4 champs par ligne
    def _row(l1, v1, s1, l2, v2, s2):
        t = Text()
        t.append(f"{l1:<9}", style="dim")
        t.append(f"{v1:>7}  ", style=s1)
        t.append(f"{l2:<9}", style="dim")
        t.append(f"{v2:>7}", style=s2)
        return t

    sep = Text("─" * 36, style="dim")
    lines_out = [
        _row("Sharpe",   _fmt_f(sh),         "white",
             "Sortino",  _fmt_f(so),         "white"),
        _row("Info.R.",  _fmt_f(ir),         "white",
             "Calmar",   _fmt_f(ca),         "white"),
        _row("Treynor",  _fmt_f(tr),         "white",
             "Omega",    _fmt_f(om),         "white"),
        _row("Alpha J.", f"{_fmt_m(ja,2)}%", ja_col,
             "Beta",     _fmt_f(b),          "white"),
        sep,
        _row("Vol.",     f"{_fmt_f(vol,1)}%", "white",
             "Skew",     _fmt_f(skew),       skew_col),
        _row("MDD",      f"{_fmt_f(mdd,1)}%", _col(mdd, True),
             "VaR 95%",  _fmt_m(var, 0),     _col(var, True)),
        _row("CVaR 95%", _fmt_m(cvar, 0),   _col(cvar, True),
             "Win Rate", wr_str,             "bright_green"),
    ]

    g = Group(*lines_out)
    return Panel(g, title="[bold bright_cyan]Risque & Metriques[/bold bright_cyan]",
                 border_style="bright_blue", box=box.ROUNDED)

def _panel_reel(rp: dict, flash: int) -> Panel:
    n_col  = _col(rp["nominal_pnl_eur"])
    r_col  = _col(rp["real_pnl_eur"])
    hl     = "bold " if flash > 0 else ""
    months = int((datetime.now() - datetime.strptime(rp["start_date"], "%Y-%m-%d")).days / 30.44)

    lines = [
        f"[dim]Capital depart :[/dim]  [white]{rp['start_capital']:>10,.0f} EUR[/white]",
        f"[dim]Valeur actuelle:[/dim]  [{hl}{n_col}]{rp['total_eur']:>10,.0f} EUR[/{hl}{n_col}]",
        f"[dim]P&L nominal    :[/dim]  [{hl}{n_col}]{_fmt_m(rp['nominal_pnl_eur'],0):>10} EUR  {_fmt_pct(rp['nominal_pnl_pct'],False)}[/{hl}{n_col}]",
        f"[dim]               [/dim]  [dim]──────────────[/dim]",
        f"[dim]Inflation ({months}m):[/dim]  [yellow]{rp['inflation_rate']*100:.1f}%[/yellow] [dim]CPI live[/dim]  [dim]erosion -[/dim][red]{rp['inflation_erosion']:,.0f} EUR[/red]",
        f"[dim]P&L reel       :[/dim]  [{hl}{r_col}]{_fmt_m(rp['real_pnl_eur'],0):>10} EUR  {_fmt_pct(rp['real_pnl_pct'],False)}[/{hl}{r_col}]",
    ]
    return Panel("\n".join(lines), title="[bold yellow]Capital Reel[/bold yellow]",
                 border_style="yellow", box=box.ROUNDED)


def _panel_classements(em: dict, flash: int) -> Panel:
    hl = "bold " if flash > 0 else ""

    def _line(label, ticker, pct):
        col = _col(pct)
        t = Text()
        t.append(f"{label} ", style="dim")
        t.append(f"{ticker:<8}", style=f"{hl}bold white")
        t.append(f" {_fmt_pct(pct, False)}", style=col)
        return t

    # Secteurs
    sector_pct = em.get("sector_pct", {})
    BAR_W = 8
    sector_lines = []
    colors = {"Tech": "bright_cyan", "Finance": "bright_green",
              "Matieres": "yellow", "Industrie": "magenta",
              "Energie": "bright_red", "Sante": "bright_blue",
              "Conso": "white", "Autre": "dim"}
    for s, pct in list(sector_pct.items())[:5]:
        filled = max(0, min(BAR_W, int(pct / 100 * BAR_W)))
        bar    = FULL * filled + LIGHT * (BAR_W - filled)
        c      = colors.get(s, "white")
        t      = Text()
        t.append(f"  {s:<9}", style="dim")
        t.append(bar, style=c)
        t.append(f" {pct:4.1f}%", style="white")
        sector_lines.append(t)

    g = Group(
        _line(f"  Jour  {UP} ", em["best_day_ticker"],  em["best_day_pct"]),
        _line(f"  Jour  {DOWN} ", em["worst_day_ticker"], em["worst_day_pct"]),
        Text("  " + "─" * 24, style="dim"),
        _line(f"  Total {UP} ", em["best_all_ticker"],  em["best_all_pct"]),
        _line(f"  Total {DOWN} ", em["worst_all_ticker"], em["worst_all_pct"]),
        Text("  " + "─" * 24, style="dim"),
        *sector_lines,
    )
    return Panel(g, title="[bold bright_cyan]Classements & Secteurs[/bold bright_cyan]",
                 border_style="bright_blue", box=box.ROUNDED)


# -----------------------------------------------------------------------
# Panel Markowitz
# -----------------------------------------------------------------------

def _panel_markowitz(mz: dict) -> Panel:
    """Bandeau compact Markowitz : résumé Sharpe + top signaux."""
    curr_sh = mz.get("curr_sharpe", float("nan"))
    opt_sh  = mz.get("opt_sharpe",  float("nan"))
    gain    = mz.get("sharpe_gain", float("nan"))
    comp    = mz.get("comparison",  [])

    gain_col = "bright_green" if (not math.isnan(gain) and gain > 0) else "bright_red"

    t = Text()
    t.append("  Sharpe actuel ", style="dim")
    t.append(f"{_fmt_f(curr_sh)}", style="bold white")
    t.append("  →  Sharpe optimal ", style="dim")
    t.append(f"{_fmt_f(opt_sh)}", style="bold bright_green")
    t.append("   gain potentiel ", style="dim")
    t.append(f"{_sign(gain)}{_fmt_f(gain)} pts  ", style=f"bold {gain_col}")
    t.append("  |  Top signaux : ", style="dim")

    # Top 6 signaux (les plus grandes déviations)
    for e in comp[:6]:
        sig = e["signal"]
        col = "bright_green" if sig == "↑" else "bright_red" if sig == "↓" else "dim"
        t.append(f"  {sig} {e['ticker']} ", style=f"bold {col}")
        t.append(f"{e['optimal_pct']:.1f}%", style=col)

    return Panel(t, title="[bold bright_magenta]Markowitz Max-Sharpe[/bold bright_magenta]",
                 border_style="bright_magenta", box=box.ROUNDED)


# -----------------------------------------------------------------------
# Dashboard principal
# -----------------------------------------------------------------------

def build_dashboard(
    positions_df,
    metrics,
    real_pnl,
    ext_metrics,
    last_update,
    next_refresh:    int  = 5,
    flash:           int  = 0,
    loading:         bool = False,
    market_ctx:      "Optional[dict]" = None,
    infl_by_ccy:     "Optional[dict]" = None,
    markowitz:       "Optional[dict]" = None,
) -> Panel:
    header = _build_header(last_update, next_refresh, flash, loading, market_ctx)

    if positions_df is None or metrics is None or real_pnl is None:
        return Panel(
            Group(header, Align.center(Text("\n  Chargement des donnees...\n", style="yellow"))),
            box=box.HEAVY_EDGE,
            border_style="bright_blue",
            padding=(0, 1),
        )

    pos_tbl  = _build_positions_table(positions_df, flash, markowitz)
    mkt_tbl  = _build_markets_table(market_ctx or {}, infl_by_ccy)
    side_grid = _GridTable.grid(expand=True, padding=(0, 1))
    side_grid.add_column(width=24, no_wrap=True)
    side_grid.add_column()
    side_grid.add_row(mkt_tbl, pos_tbl)
    tbl = side_grid

    col_val  = _panel_valorisation(metrics, real_pnl, ext_metrics, flash)
    col_risk = _panel_risque(metrics, ext_metrics)
    col_cap  = _panel_reel(real_pnl, flash)
    col_cls  = _panel_classements(ext_metrics, flash)

    metrics_row = Columns(
        [col_val, col_risk, col_cap, col_cls],
        expand=True,
        equal=False,
    )

    elements = [header, Rule(style="dim"), tbl, Rule(style="dim"), metrics_row]
    if markowitz:
        elements += [Rule(style="dim"), _panel_markowitz(markowitz)]
    body = Group(*elements)
    return Panel(
        body,
        box=box.HEAVY_EDGE,
        border_style="bright_blue",
        padding=(0, 1),
    )
