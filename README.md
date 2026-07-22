# 📈 Terminal Portfolio Tracker

A real-time, terminal-based portfolio dashboard built from scratch in Python — designed to monitor a multi-currency equity portfolio with live market data, risk metrics, and portfolio optimization.

---

## Why I Built This

As a finance student interested in markets and quantitative analysis, I wanted to go beyond spreadsheet tracking. This project gave me hands-on experience with live market data pipelines, multi-currency P&L accounting, and institutional portfolio construction techniques — all rendered in a professional terminal UI.

---

## Features

### Live Market Data
- **Real-time prices** via `yfinance` — equities across NYSE, NASDAQ, TSX, Euronext, SIX Swiss Exchange, XETRA
- **Multi-currency FX** — USD, EUR, CHF, CAD, GBP live rates, all positions consolidated in EUR
- **Market context panel** — S&P 500, VIX, Gold, Oil live with YTD performance

### P&L & Risk Metrics
- **Nominal P&L** and **inflation-adjusted real P&L** (BLS CPI for USD, ECB HICP for EUR, World Bank for CHF/CAD)
- **YTD return** vs. S&P 500 benchmark (live intraday pricing)
- **Sharpe ratio, Information ratio, Beta, Max Drawdown, Volatility** — computed on 1-year daily returns
- **Position-level P&L** in both local currency and EUR

### Markowitz Portfolio Optimization (Max-Sharpe)
- **Split-window approach**: covariance matrix on **3 years** of data (stable, long-term correlations), expected returns on **1 year** (reactive to recent trends) — institutional standard
- **SLSQP optimization** via `scipy.optimize` with max 30% weight per position
- Per-position **Optimal Weight %** and **Signal** (Overweight / Underweight / ~Neutral) displayed inline
- Sharpe: current portfolio vs. optimal portfolio shown in a dedicated panel

### Terminal UI
- Built with `Rich` — live-refreshing dashboard with panels, colored tables, and P&L sparklines
- Auto-refresh every 5 seconds (configurable)
- Graceful handling of closed markets (European/Swiss exchanges after hours)

---

## Tech Stack

| Library | Use |
|---|---|
| `yfinance` | Live & historical market data |
| `pandas` / `numpy` | Data manipulation & return computation |
| `scipy` | Markowitz SLSQP optimization |
| `rich` | Terminal UI (Live, Panel, Table) |

---

## Getting Started

```bash
# 1. Clone
git clone https://github.com/Ottlow/portfolio-tracker.git
cd portfolio-tracker

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit portfolio.csv with your positions
# ticker, quantity, avg_cost (in local currency)

# 4. Run
python main.py
```

**Optional flags:**
```bash
python main.py --file my_portfolio.csv --refresh 10
```

---

## Portfolio Format

`portfolio.csv` — one row per position:

```csv
ticker,quantity,avg_cost
MSFT,20,400.00
ASML,3,680.00
TTE.PA,50,60.00
```

Tickers follow Yahoo Finance conventions (e.g. `SIE.DE` for Siemens on XETRA, `AEM.TO` for Agnico on TSX).

---

## Architecture

```
main.py          → entry point, refresh loop
fetcher.py       → yfinance data layer (historical + live + FX + inflation)
metrics.py       → P&L, Sharpe, Beta, Drawdown, Markowitz optimization
display.py       → Rich terminal layout
portfolio.csv    → position input
```

---

## Key Design Decisions

- **Split-window Markowitz** (3y cov / 1y mu): classical Markowitz on 1y only tends to over-concentrate in recent winners. Using a longer covariance window produces more stable, diversified optimal portfolios — consistent with how institutional desks calibrate their models.
- **Inflation-adjusted P&L**: real return matters for performance attribution. Each currency uses its own official inflation source (BLS, ECB, World Bank), cached for 6 hours.
- **Per-ticker last non-NaN fallback**: when European or Swiss markets close before the tracker refreshes, `yfinance` returns NaN for the last row. The fetcher explicitly searches backwards for the last valid price per ticker, preventing `N/A` display errors.

---

## Background

Built as a personal project alongside my finance studies to deepen my understanding of portfolio construction, risk metrics, and market data infrastructure. The data flow (fetch → normalize → compute → display) mirrors what you'd find in a professional trading desk toolkit, scaled to what a single developer can build cleanly in Python.

---

*Demo portfolio shown — fictional positions for illustration.*
