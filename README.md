# Terminal Portfolio Tracker

Real-time terminal dashboard for a multi-currency equity portfolio: live prices, risk metrics, and Markowitz optimization, all in the terminal.
<img width="1894" height="1019" alt="image" src="https://github.com/user-attachments/assets/37ff1f34-2b04-4598-8487-4d6c1c7d8008" />

<img width="1907" height="880" alt="image" src="https://github.com/user-attachments/assets/2269b086-e479-47f9-85d9-ac9422479932" />



---

## Why I Built This

As a finance student interested in markets and quant, I wanted to go beyond spreadsheet tracking. This project gave me hands-on experience with live market data pipelines, multi-currency P&L accounting, and portfolio construction techniques rendered in a terminal UI.

---

## Features

### Live Market Data
- **Real-time prices** via `yfinance` across NYSE, NASDAQ, TSX, Euronext, SIX Swiss Exchange, XETRA
- **Multi-currency FX**: USD, EUR, CHF, CAD, GBP rates, all positions consolidated in EUR
- **Market context panel**: S&P 500, VIX, Gold, Oil with YTD performance

### P&L & Risk Metrics
- **Nominal P&L** and **inflation-adjusted real P&L** (BLS CPI for USD, ECB HICP for EUR, World Bank for CHF/CAD)
- **YTD return** vs. S&P 500 benchmark (live intraday)
- **Sharpe, Information ratio, Beta, Max Drawdown, Volatility** computed on 1-year daily returns
- **Position-level P&L** in local currency and EUR

### Markowitz Portfolio Optimization (Max-Sharpe)
- **Split-window approach**: covariance matrix on **3 years** of data (stable long-term correlations), expected returns on **1 year** (reactive to recent trends). Closer to how institutional desks actually calibrate these models.
- **SLSQP optimization** via `scipy.optimize`, max 30% weight per position
- Per-position optimal weight and rebalancing signal displayed inline

### Terminal UI
- Built with `Rich`: live-refreshing dashboard with panels, colored tables, and sector bar charts
- Auto-refresh every 5 seconds (configurable)
- Handles closed markets gracefully (European/Swiss exchanges after hours)

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

`portfolio.csv`, one row per position:

```csv
ticker,quantity,avg_cost
MSFT,20,400.00
ASML,3,680.00
TTE.PA,50,60.00
```

Tickers follow Yahoo Finance conventions (e.g. `SIE.DE` for Siemens on XETRA, `AEM.TO` for Agnico Eagle on TSX).

---

## Architecture

```
main.py          -> entry point, refresh loop
fetcher.py       -> yfinance data layer (historical + live + FX + inflation)
metrics.py       -> P&L, Sharpe, Beta, Drawdown, Markowitz optimization
display.py       -> Rich terminal layout
portfolio.csv    -> position input
```

---

## Key Design Decisions

- **Split-window Markowitz** (3y cov / 1y mu): running Markowitz purely on 1y data tends to over-concentrate in recent winners. A longer covariance window gives more stable, diversified allocations.
- **Inflation-adjusted P&L**: each currency pulls from its own official source (BLS, ECB, World Bank), cached for 6 hours.
- **Per-ticker non-NaN fallback**: when European or Swiss markets close before the tracker refreshes, `yfinance` returns NaN on the last row. The fetcher searches backwards for the last valid price per ticker to avoid N/A display errors.

---

## Background

Personal project built alongside my finance studies. The data flow (fetch -> normalize -> compute -> display) roughly mirrors what you'd find in a trading desk toolkit, at a scale one person can build cleanly in Python.

---

*Demo portfolio shown. Fictional positions for illustration.*
