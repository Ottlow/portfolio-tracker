"""
metrics.py - Calculs financiers : P&L, risque, change, inflation.
"""

from __future__ import annotations

import math
from typing import Optional
from datetime import datetime

import numpy as np
import pandas as pd

from fetcher import MarketData

# -----------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL  = 0.03

START_CAPITAL_EUR = 128_987.61   # 138 850 – 9 862.39 (BRK-B proceeds retirés Jul-20)
START_DATE        = "2024-03-01"

_INFLATION_BY_YEAR = {
    2024: 0.024,   # CPI US annuel moyen
    2025: 0.038,   # CPI US annuel moyen 2025
    2026: 0.035,   # CPI US juin 2026 (BLS, release 14/07/2026)
}

# Secteurs par ticker
SECTORS: dict[str, str] = {
    'GOOGL': 'Tech',    'AMZN':    'Tech',     'ASML':    'Tech',
    'CSCO':  'Tech',    'META':    'Tech',      'MSFT':    'Tech',
    'NVDA':  'Tech',    'TSM':     'Tech',
    'GS':    'Finance', 'ICE':     'Finance',   'MAIN':    'Finance',
    'SCHP.SW':'Finance','V':       'Finance',   'ZURN.SW': 'Finance',
    'CMBN.SW':'Finance','BRK-B':   'Finance',
    'ISRG':  'Sante',
    'SIE.DE':'Industrie','LIN':    'Industrie',
    'TTE.PA':'Energie',
    'AEM.TO':'Matieres','COTN.SW': 'Matieres', 'RIO':     'Matieres',
    'MC.PA': 'Conso',   'PDD':     'Conso',
}

# -----------------------------------------------------------------------
# Devise & conversion
# -----------------------------------------------------------------------

def infer_currency(ticker: str) -> str:
    t = ticker.upper()
    if any(t.endswith(s) for s in ('.PA', '.DE', '.AS', '.BR', '.MI', '.MC', '.LS')):
        return 'EUR'
    if any(t.endswith(s) for s in ('.SW', '.VX')):
        return 'CHF'
    if t.endswith('.TO'):
        return 'CAD'
    if t.endswith('.L'):
        return 'GBP'
    return 'USD'


def to_eur(amount: float, currency: str, fx: dict) -> float:
    if math.isnan(amount):
        return float("nan")
    if currency == 'EUR':
        return amount
    rate = fx.get(currency)
    if not rate or rate == 0:
        return float("nan")
    return amount / rate


# -----------------------------------------------------------------------
# Inflation cumulee
# -----------------------------------------------------------------------

def compute_cumulative_inflation(
    start_date: str = START_DATE,
    live_rates: Optional[dict] = None,
    currency: str = "USD",
) -> float:
    if live_rates and isinstance(next(iter(live_rates)), str) and not next(iter(live_rates)).isdigit():
        ccy_rates = live_rates.get(currency, {})
    elif live_rates:
        ccy_rates = {k: v for k, v in live_rates.items() if isinstance(k, int)}
    else:
        ccy_rates = {}

    rates = dict(_INFLATION_BY_YEAR)
    rates.update(ccy_rates)

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end   = datetime.now()
    cumulative = 1.0
    yr, mo = start.year, start.month
    while datetime(yr, mo, 1) < datetime(end.year, end.month, 1):
        annual_rate  = rates.get(yr, 0.025)
        monthly_rate = (1 + annual_rate) ** (1 / 12) - 1
        cumulative  *= (1 + monthly_rate)
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
    return cumulative - 1.0


# -----------------------------------------------------------------------
# Metriques par position
# -----------------------------------------------------------------------

def compute_positions(portfolio: pd.DataFrame, market_data: MarketData) -> pd.DataFrame:
    df  = portfolio.copy()
    snp = market_data.snapshots
    fx  = market_data.fx_rates
    hist = market_data.historical

    def _get(ticker, attr, default=float("nan")):
        s = snp.get(ticker)
        return getattr(s, attr, default) if s else default

    df["ticker_currency"] = df["ticker"].map(infer_currency)
    df["current_price"]   = df["ticker"].map(lambda t: _get(t, "price"))
    df["prev_close"]      = df["ticker"].map(lambda t: _get(t, "prev_close"))
    df["day_change_pct"]  = df["ticker"].map(lambda t: _get(t, "day_change_pct", 0.0))

    df["market_value"] = df["quantity"] * df["current_price"]
    df["cost_basis"]   = df["quantity"] * df["avg_cost"]
    df["pnl"]          = df["market_value"] - df["cost_basis"]
    df["pnl_pct"]      = (df["pnl"] / df["cost_basis"]) * 100

    df["market_value_eur"] = df.apply(
        lambda r: to_eur(float(r["market_value"]), r["ticker_currency"], fx), axis=1
    )
    df["pnl_eur"] = df.apply(
        lambda r: to_eur(float(r["pnl"]), r["ticker_currency"], fx), axis=1
    )

    df["day_pnl"] = df.apply(
        lambda r: r["quantity"] * (r["current_price"] - r["prev_close"])
        if not (math.isnan(r["current_price"]) or math.isnan(r["prev_close"]))
        else float("nan"), axis=1
    )
    df["day_pnl_eur"] = df.apply(
        lambda r: to_eur(float(r["day_pnl"]), r["ticker_currency"], fx)
        if not math.isnan(r["day_pnl"]) else float("nan"), axis=1
    )

    df["sector"] = df["ticker"].map(lambda t: SECTORS.get(t, "Autre"))

    total_native = float(df["market_value"].sum())
    total_eur    = float(df["market_value_eur"].sum())

    df["weight"]     = df["market_value"]     / total_native * 100 if total_native > 0 else 0.0
    df["weight_eur"] = df["market_value_eur"] / total_eur    * 100 if total_eur    > 0 else 0.0

    return df


# -----------------------------------------------------------------------
# P&L reel (change + inflation)
# -----------------------------------------------------------------------

def compute_real_pnl(
    positions_df: pd.DataFrame,
    fx_rates: dict,
    start_capital: float = START_CAPITAL_EUR,
    start_date: str      = START_DATE,
    live_inflation: Optional[dict] = None,
) -> dict:
    total_eur = float(positions_df["market_value_eur"].sum())

    nominal_pnl_eur = total_eur - start_capital
    nominal_pnl_pct = nominal_pnl_eur / start_capital * 100 if start_capital else 0.0

    def _infl(ccy: str) -> float:
        return compute_cumulative_inflation(start_date, live_rates=live_inflation, currency=ccy)

    if "market_value_eur" in positions_df.columns:
        total_val = float(positions_df["market_value_eur"].sum())
        weighted_infl = 0.0
        for ccy in ["USD", "EUR", "CHF", "CAD"]:
            sub = positions_df[positions_df["ticker_currency"] == ccy]
            if not sub.empty and total_val > 0:
                w = float(sub["market_value_eur"].sum()) / total_val
                weighted_infl += _infl(ccy) * w
        inflation_rate = weighted_infl if weighted_infl > 0 else _infl("USD")
    else:
        inflation_rate = _infl("USD")

    inflation_erosion = start_capital * inflation_rate
    real_capital      = start_capital * (1 + inflation_rate)

    real_pnl_eur = total_eur - real_capital
    real_pnl_pct = real_pnl_eur / real_capital * 100 if real_capital else 0.0

    fx_breakdown: dict = {}
    for currency in ["EUR", "USD", "CHF", "CAD"]:
        subset = positions_df[positions_df["ticker_currency"] == currency]
        if not subset.empty:
            fx_breakdown[currency] = float(subset["market_value_eur"].sum())

    return {
        "total_eur":         total_eur,
        "start_capital":     start_capital,
        "start_date":        start_date,
        "nominal_pnl_eur":   nominal_pnl_eur,
        "nominal_pnl_pct":   nominal_pnl_pct,
        "inflation_rate":    inflation_rate,
        "inflation_erosion": inflation_erosion,
        "real_capital":      real_capital,
        "real_pnl_eur":      real_pnl_eur,
        "real_pnl_pct":      real_pnl_pct,
        "fx_rates":          fx_rates,
        "fx_breakdown":      fx_breakdown,
    }


# -----------------------------------------------------------------------
# Metriques etendues : YTD, alpha, win rate, tops/flops, secteurs, jour
# -----------------------------------------------------------------------

def compute_extended_metrics(
    positions_df: pd.DataFrame,
    market_data:  MarketData,
    fx_rates:     dict,
) -> dict:
    hist    = market_data.historical
    mkt_sym = market_data.market_ticker
    now     = datetime.now()
    ytd_start = pd.Timestamp(f"{now.year}-01-01")

    idx = hist.index
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_localize(None)
    hist_ytd    = hist[idx >= ytd_start]
    ytd_pnl_eur = float("nan")
    ytd_pnl_pct = float("nan")
    ytd_spx_pct = float("nan")

    if not hist_ytd.empty:
        first = hist_ytd.iloc[0]

        def _live_price(ticker):
            snap = market_data.snapshots.get(ticker)
            if snap and not math.isnan(snap.price):
                return snap.price
            last = hist.iloc[-1]
            v = last[ticker] if ticker in last.index else float("nan")
            return float(v) if not pd.isna(v) else float("nan")

        ytd_pnl_nat  = 0.0
        ytd_base_nat = 0.0
        for _, row in positions_df.iterrows():
            t, qty, ccy = row["ticker"], row["quantity"], row["ticker_currency"]
            if t not in first.index or pd.isna(first[t]):
                continue
            p0 = float(first[t])
            p1 = _live_price(t)
            if math.isnan(p0) or math.isnan(p1) or p0 == 0:
                continue
            ytd_pnl_nat  += to_eur(qty * (p1 - p0), ccy, fx_rates)
            ytd_base_nat += to_eur(qty * p0,         ccy, fx_rates)

        if ytd_base_nat > 0:
            ytd_pnl_eur = ytd_pnl_nat
            ytd_pnl_pct = ytd_pnl_nat / ytd_base_nat * 100

        if mkt_sym in hist_ytd.columns:
            p0_raw = first.get(mkt_sym, float("nan"))
            p0_spx = float(p0_raw) if not pd.isna(p0_raw) else float("nan")
            live_ctx = market_data.market_context.get(mkt_sym, {})
            live_spx = live_ctx.get("price", float("nan"))
            if not math.isnan(live_spx):
                p1_spx = live_spx
            else:
                last = hist.iloc[-1]
                p1_raw = last[mkt_sym] if mkt_sym in last.index else float("nan")
                p1_spx = float(p1_raw) if not pd.isna(p1_raw) else float("nan")
            if (not math.isnan(p0_spx)) and p0_spx > 0 and (not math.isnan(p1_spx)):
                ytd_spx_pct = (p1_spx - p0_spx) / p0_spx * 100

    alpha_ytd = (
        ytd_pnl_pct - ytd_spx_pct
        if not (math.isnan(ytd_pnl_pct) or math.isnan(ytd_spx_pct))
        else float("nan")
    )

    winners   = int((positions_df["pnl"] > 0).sum())
    total_pos = len(positions_df)
    win_rate  = winners / total_pos * 100 if total_pos > 0 else float("nan")

    valid_day = positions_df.dropna(subset=["day_change_pct"])
    best_day  = valid_day.loc[valid_day["day_change_pct"].idxmax()] if not valid_day.empty else None
    worst_day = valid_day.loc[valid_day["day_change_pct"].idxmin()] if not valid_day.empty else None

    valid_all = positions_df.dropna(subset=["pnl_pct"])
    best_all  = valid_all.loc[valid_all["pnl_pct"].idxmax()] if not valid_all.empty else None
    worst_all = valid_all.loc[valid_all["pnl_pct"].idxmin()] if not valid_all.empty else None

    def _t(row): return str(row["ticker"]) if row is not None else "--"
    def _v(row, k): return float(row[k]) if row is not None else float("nan")

    daily_pnl_eur = float(positions_df["day_pnl_eur"].sum())
    total_eur     = float(positions_df["market_value_eur"].sum())
    prev_total    = total_eur - daily_pnl_eur
    daily_pnl_pct = (daily_pnl_eur / prev_total * 100) if prev_total > 0 else float("nan")

    sector_exp: dict = {}
    for _, row in positions_df.iterrows():
        s  = SECTORS.get(str(row["ticker"]), "Autre")
        mv = row.get("market_value_eur", 0)
        if not math.isnan(float(mv)):
            sector_exp[s] = sector_exp.get(s, 0.0) + float(mv)
    total_exp = sum(sector_exp.values())
    sector_pct = {
        k: v / total_exp * 100
        for k, v in sorted(sector_exp.items(), key=lambda x: -x[1])
    } if total_exp > 0 else {}

    return {
        "ytd_pnl_eur":      ytd_pnl_eur,
        "ytd_pnl_pct":      ytd_pnl_pct,
        "ytd_spx_pct":      ytd_spx_pct,
        "alpha_ytd":        alpha_ytd,
        "win_rate":         win_rate,
        "winners":          winners,
        "total_pos":        total_pos,
        "daily_pnl_eur":    daily_pnl_eur,
        "daily_pnl_pct":    daily_pnl_pct,
        "sector_pct":       sector_pct,
        "best_day_ticker":  _t(best_day),
        "best_day_pct":     _v(best_day,  "day_change_pct"),
        "worst_day_ticker": _t(worst_day),
        "worst_day_pct":    _v(worst_day, "day_change_pct"),
        "best_all_ticker":  _t(best_all),
        "best_all_pct":     _v(best_all,  "pnl_pct"),
        "worst_all_ticker": _t(worst_all),
        "worst_all_pct":    _v(worst_all, "pnl_pct"),
    }


# -----------------------------------------------------------------------
# Metriques de risque portefeuille
# -----------------------------------------------------------------------

def _daily_returns(prices):
    return prices.pct_change().dropna()


def _sharpe(returns: pd.Series) -> float:
    if returns.empty or returns.std() == 0:
        return float("nan")
    rf_daily = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    return float(np.sqrt(TRADING_DAYS_PER_YEAR) * (returns.mean() - rf_daily) / returns.std())


def _sortino(returns: pd.Series) -> float:
    if returns.empty or len(returns) < 10:
        return float("nan")
    rf_daily = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    downside_sq  = np.minimum(returns.values - rf_daily, 0) ** 2
    downside_dev = np.sqrt(np.mean(downside_sq) * TRADING_DAYS_PER_YEAR)
    if downside_dev == 0:
        return float("nan")
    ann_excess = (returns.mean() - rf_daily) * TRADING_DAYS_PER_YEAR
    return float(ann_excess / downside_dev)


def _information_ratio(port_returns: pd.Series, mkt_returns: pd.Series) -> float:
    aligned = pd.concat([port_returns, mkt_returns], axis=1).dropna()
    if aligned.empty or aligned.shape[0] < 10:
        return float("nan")
    excess = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    if excess.std() == 0:
        return float("nan")
    return float(np.sqrt(TRADING_DAYS_PER_YEAR) * excess.mean() / excess.std())


def _calmar(port_cum: pd.Series, port_returns: pd.Series) -> float:
    mdd = _max_drawdown(port_cum)
    if math.isnan(mdd) or mdd == 0:
        return float("nan")
    n = len(port_returns)
    if n == 0:
        return float("nan")
    total_ret = float(port_cum.iloc[-1]) - 1.0
    cagr_pct  = ((1 + total_ret) ** (TRADING_DAYS_PER_YEAR / n) - 1) * 100
    return cagr_pct / abs(mdd)


def _beta(asset: pd.Series, market: pd.Series) -> float:
    al = pd.concat([asset, market], axis=1).dropna()
    if al.shape[0] < 10 or al.iloc[:, 1].var() == 0:
        return float("nan")
    cov = np.cov(al.iloc[:, 0], al.iloc[:, 1])
    return float(cov[0, 1] / cov[1, 1])


def _max_drawdown(prices: pd.Series) -> float:
    if prices.empty:
        return float("nan")
    return float(((prices - prices.cummax()) / prices.cummax()).min() * 100)


def _volatility(returns: pd.Series) -> float:
    if returns.empty or returns.std() == 0:
        return float("nan")
    return float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR) * 100)


def _var95(returns: pd.Series, value: float) -> float:
    if returns.empty:
        return float("nan")
    return float(returns.quantile(0.05) * value)


def _cvar(returns: pd.Series, value: float, confidence: float = 0.95) -> float:
    if returns.empty:
        return float("nan")
    threshold = returns.quantile(1 - confidence)
    tail = returns[returns <= threshold]
    if tail.empty:
        return float("nan")
    return float(tail.mean() * value)


def _skewness(returns: pd.Series) -> float:
    if returns.empty or len(returns) < 10:
        return float("nan")
    return float(returns.skew())


def _omega_ratio(returns: pd.Series) -> float:
    if returns.empty:
        return float("nan")
    rf_daily = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    gains  = (returns[returns > rf_daily] - rf_daily).sum()
    losses = (rf_daily - returns[returns <= rf_daily]).sum()
    if losses == 0:
        return float("nan")
    return float(gains / losses)


def _treynor(returns: pd.Series, market: pd.Series) -> float:
    b = _beta(returns, market)
    if math.isnan(b) or b == 0:
        return float("nan")
    rf_d       = RISK_FREE_RATE_ANNUAL / TRADING_DAYS_PER_YEAR
    ann_excess = (returns.mean() - rf_d) * TRADING_DAYS_PER_YEAR
    return float(ann_excess / b)


def _jensen_alpha(returns: pd.Series, market: pd.Series) -> float:
    b = _beta(returns, market)
    if math.isnan(b):
        return float("nan")
    mkt_aligned = market.reindex(returns.index).dropna()
    ret_aligned = returns.reindex(mkt_aligned.index)
    ann_port = ret_aligned.mean() * TRADING_DAYS_PER_YEAR * 100
    ann_mkt  = mkt_aligned.mean() * TRADING_DAYS_PER_YEAR * 100
    expected = RISK_FREE_RATE_ANNUAL * 100 + b * (ann_mkt - RISK_FREE_RATE_ANNUAL * 100)
    return float(ann_port - expected)


def compute_markowitz_optimization(
    positions_df: pd.DataFrame,
    market_data:  MarketData,
    fx_rates:     dict,
    risk_free_rate: float = RISK_FREE_RATE_ANNUAL,
    max_weight:   float = 0.30,
) -> dict:
    """
    Optimisation Markowitz max-Sharpe avec split window institutionnel :
      - Covariance  : 3 ans (stable, capture cycles bull/bear)
      - Mu (returns): 1 an  (reactif aux conditions actuelles)
    """
    try:
        from scipy.optimize import minimize
        import yfinance as yf
    except ImportError:
        return {}

    hist_1y = market_data.historical
    tickers  = [r["ticker"] for _, r in positions_df.iterrows()
                if r["ticker"] in hist_1y.columns]
    if len(tickers) < 3:
        return {}

    try:
        raw_3y = yf.download(
            " ".join(tickers), period="3y",
            auto_adjust=True, progress=False,
        )
        hist_3y = (raw_3y["Close"] if isinstance(raw_3y.columns, pd.MultiIndex)
                   else raw_3y[["Close"]].rename(columns={"Close": tickers[0]}))
        hist_3y = hist_3y.dropna(how="all")
        if hasattr(hist_3y.index, "tz") and hist_3y.index.tz is not None:
            hist_3y.index = hist_3y.index.tz_localize(None)
    except Exception:
        hist_3y = hist_1y

    ret_3y = hist_3y[tickers].copy().pct_change().dropna(how="all")
    valid   = [t for t in tickers if ret_3y[t].isna().mean() < 0.20]
    if len(valid) < 3:
        return {}
    ret_3y   = ret_3y[valid].dropna()
    tickers  = valid

    cutoff_1y = ret_3y.index[-1] - pd.DateOffset(years=1)
    ret_1y    = ret_3y[ret_3y.index >= cutoff_1y]
    if len(ret_1y) < 60 or len(ret_3y) < 120:
        return {}

    mu  = ret_1y.mean().values  * TRADING_DAYS_PER_YEAR
    cov = ret_3y.cov().values   * TRADING_DAYS_PER_YEAR
    n   = len(tickers)
    rf  = risk_free_rate

    def neg_sharpe(w):
        w   = np.asarray(w)
        ret = float(w @ mu)
        vol = float(np.sqrt(w @ cov @ w))
        return -(ret - rf) / vol if vol > 1e-9 else 0.0

    res = minimize(
        neg_sharpe,
        x0      = np.ones(n) / n,
        method  = "SLSQP",
        bounds  = [(0.0, max_weight)] * n,
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
        options = {"ftol": 1e-10, "maxiter": 2000},
    )
    if not res.success:
        return {}

    opt_w      = np.clip(res.x, 0, None)
    opt_w     /= opt_w.sum()
    opt_sharpe = -res.fun

    total_eur   = float(positions_df["market_value_eur"].sum())
    curr_w_map  = {
        r["ticker"]: float(r["market_value_eur"]) / total_eur
        for _, r in positions_df.iterrows()
        if total_eur > 0
    }

    curr_arr = np.array([curr_w_map.get(t, 0.0) for t in tickers])
    curr_arr /= curr_arr.sum() if curr_arr.sum() > 0 else 1.0
    curr_ret  = float(curr_arr @ mu)
    curr_vol  = float(np.sqrt(curr_arr @ cov @ curr_arr))
    curr_sharpe = (curr_ret - rf) / curr_vol if curr_vol > 1e-9 else float("nan")

    comparison = []
    for i, t in enumerate(tickers):
        opt  = float(opt_w[i])
        curr = curr_w_map.get(t, 0.0)
        diff = opt - curr
        if diff >  0.025:  signal = "↑"
        elif diff < -0.025: signal = "↓"
        else:               signal = "✓"
        comparison.append({
            "ticker":      t,
            "current_pct": curr * 100,
            "optimal_pct": opt  * 100,
            "diff_pct":    diff * 100,
            "signal":      signal,
        })
    comparison.sort(key=lambda x: -abs(x["diff_pct"]))

    return {
        "curr_sharpe": curr_sharpe,
        "opt_sharpe":  opt_sharpe,
        "sharpe_gain": opt_sharpe - curr_sharpe,
        "comparison":  comparison,
        "n_tickers":   n,
    }


def compute_portfolio_metrics(positions_df: pd.DataFrame, market_data: MarketData) -> dict:
    hist    = market_data.historical
    mkt_sym = market_data.market_ticker
    ret_df  = _daily_returns(hist)

    available   = [t for t in positions_df["ticker"] if t in ret_df.columns]
    mkt_returns = ret_df[mkt_sym] if mkt_sym in ret_df.columns else pd.Series(dtype=float)

    weights = positions_df.set_index("ticker")["weight"].reindex(available).fillna(0) / 100
    port_returns = ret_df[available].mul(weights, axis=1).sum(axis=1) if available else pd.Series(dtype=float)

    total_value = float(positions_df["market_value"].sum())
    total_cost  = float(positions_df["cost_basis"].sum())
    total_pnl   = total_value - total_cost
    port_cum    = (1 + port_returns).cumprod()

    ticker_metrics = {}
    for t in available:
        ticker_metrics[t] = {
            "sharpe":       _sharpe(ret_df[t]),
            "volatility":   _volatility(ret_df[t]),
            "beta":         _beta(ret_df[t], mkt_returns) if not mkt_returns.empty else float("nan"),
            "max_drawdown": _max_drawdown(hist[t]),
        }

    mkt = mkt_returns if not mkt_returns.empty else pd.Series(dtype=float)
    return {
        "total_value":       total_value,
        "total_cost":        total_cost,
        "total_pnl":         total_pnl,
        "total_pnl_pct":     total_pnl / total_cost * 100 if total_cost else float("nan"),
        "sharpe":            _sharpe(port_returns),
        "sortino":           _sortino(port_returns),
        "information_ratio": _information_ratio(port_returns, mkt) if not mkt.empty else float("nan"),
        "calmar":            _calmar(port_cum, port_returns),
        "treynor":           _treynor(port_returns, mkt) if not mkt.empty else float("nan"),
        "omega":             _omega_ratio(port_returns),
        "jensen_alpha":      _jensen_alpha(port_returns, mkt) if not mkt.empty else float("nan"),
        "volatility":        _volatility(port_returns),
        "beta":              _beta(port_returns, mkt) if not mkt.empty else float("nan"),
        "max_drawdown":      _max_drawdown(port_cum),
        "var_95":            _var95(port_returns, total_value),
        "cvar_95":           _cvar(port_returns, total_value),
        "skewness":          _skewness(port_returns),
        "ticker_metrics":    ticker_metrics,
    }
