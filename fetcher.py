"""
fetcher.py - Donnees de marche via Yahoo Finance.

Strategie :
  1. yf.download(1y, daily)  -> historical (Sharpe, Beta, YTD, etc.)
  2. yf.download(1d, 1m)     -> prix live intraday (actualises chaque refresh)
  3. yf.download(5d, fx)     -> taux de change EUR/XXX
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import json
import os
import time
import urllib.request

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class TickerSnapshot:
    """Prix courant et variation journaliere d'un titre."""
    ticker: str
    name: str
    price: float
    prev_close: float
    day_change: float
    day_change_pct: float
    currency: str
    error: Optional[str] = None


@dataclass
class MarketData:
    """Donnees de marche completes : prix, historique, taux de change."""
    snapshots: dict[str, TickerSnapshot] = field(default_factory=dict)
    historical: pd.DataFrame = field(default_factory=pd.DataFrame)
    market_ticker: str = "^GSPC"
    fx_rates: dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    market_context: dict = field(default_factory=dict)
    inflation_by_currency: dict = field(default_factory=dict)  # {ccy: {year: rate}}


class DataFetcher:
    """
    Recupere les donnees de marche via Yahoo Finance.

    Parameters
    ----------
    tickers : list[str]
    market_ticker : str   - indice de reference (Sharpe/beta)
    history_period : str  - periode historique yfinance
    """

    _EXTRA = ["^VIX", "GC=F", "BTC-USD", "CL=F", "EURUSD=X", "EURCHF=X", "EURCAD=X"]

    _FX_PAIRS = {
        "USD": "EURUSD=X",
        "CHF": "EURCHF=X",
        "CAD": "EURCAD=X",
    }
    _FX_FALLBACK = {"EUR": 1.0, "USD": 1.08, "CHF": 0.94, "CAD": 1.47}
    _CPI_CACHE_TTL = 3600 * 6  # Refresh toutes les 6h

    def __init__(
        self,
        tickers: list[str],
        market_ticker: str = "^GSPC",
        history_period: str = "1y",
    ) -> None:
        self.tickers = tickers
        self.market_ticker = market_ticker
        self.history_period = history_period

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def fetch_all(self) -> MarketData:
        """Telecharge tout : historique daily + live intraday + FX."""
        closes    = self._fetch_closes()       # 1y daily - pour metriques
        live      = self._fetch_live()         # 1d 1m   - pour prix temps reel
        snapshots = self._build_snapshots(closes, live)
        fx_rates  = self._fetch_fx_rates()
        mkt_ctx      = self._build_market_context(closes, live, fx_rates)
        inflation_r  = self._fetch_all_cpi_rates()

        return MarketData(
            snapshots=snapshots,
            historical=closes,
            market_ticker=self.market_ticker,
            fx_rates=fx_rates,
            timestamp=datetime.now(),
            market_context=mkt_ctx,
            inflation_by_currency=inflation_r,
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _fetch_closes(self) -> pd.DataFrame:
        """Telecharge 1 an de cours de cloture journaliers."""
        all_tickers = self.tickers + [self.market_ticker]
        raw = yf.download(
            " ".join(all_tickers),
            period=self.history_period,
            auto_adjust=True,
            progress=False,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw["Close"]
        else:
            closes = raw[["Close"]]
            closes.columns = [all_tickers[0]]
        return closes.dropna(how="all")

    def _fetch_live(self) -> pd.DataFrame:
        """
        Telecharge les prix intraday (1 minute) de la seance en cours.
        Retourne un DataFrame avec les derniers prix disponibles.
        """
        all_tickers = self.tickers + [self.market_ticker, "^VIX"]
        try:
            raw = yf.download(
                " ".join(all_tickers),
                period="1d",
                interval="1m",
                auto_adjust=True,
                progress=False,
            )
            if raw.empty:
                return pd.DataFrame()
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Close"]
            else:
                closes = raw[["Close"]]
                closes.columns = [all_tickers[0]]
            return closes.dropna(how="all")
        except Exception as exc:
            logger.warning("Erreur fetch live intraday : %s", exc)
            return pd.DataFrame()

    def _build_snapshots(
        self,
        closes: pd.DataFrame,
        live: pd.DataFrame,
    ) -> dict[str, TickerSnapshot]:
        """
        Construit les snapshots.
        - prix courant  : live intraday > derniere cloture non-NaN du ticker
        - prev_close    : avant-derniere cloture non-NaN du ticker
        Utilise la derniere valeur non-NaN PAR TICKER pour eviter les N/A
        sur les marches fermes (EU/CH apres cloture).
        """
        result: dict[str, TickerSnapshot] = {}
        if len(closes) < 2:
            return result

        # Prix live intraday (derniere ligne)
        last_live = live.iloc[-1] if not live.empty else None

        for ticker in self.tickers:
            if ticker not in closes.columns:
                result[ticker] = TickerSnapshot(
                    ticker=ticker, name=ticker,
                    price=float("nan"), prev_close=float("nan"),
                    day_change=0.0, day_change_pct=0.0, currency="",
                    error="Introuvable dans les donnees Yahoo",
                )
                continue

            # Derniere et avant-derniere valeur non-NaN pour ce ticker specifique
            ticker_hist = closes[ticker].dropna()
            if ticker_hist.empty:
                result[ticker] = TickerSnapshot(
                    ticker=ticker, name=ticker,
                    price=float("nan"), prev_close=float("nan"),
                    day_change=0.0, day_change_pct=0.0, currency="",
                    error="Pas de donnees historiques",
                )
                continue

            last_hist  = float(ticker_hist.iloc[-1])
            prev_hist  = float(ticker_hist.iloc[-2]) if len(ticker_hist) >= 2 else last_hist

            # Prix courant : live intraday en priorite, fallback sur dernier daily non-NaN
            if last_live is not None and ticker in last_live.index and not pd.isna(last_live[ticker]):
                price = float(last_live[ticker])
            else:
                price = last_hist

            prev_close = prev_hist
            change     = price - prev_close
            change_pct = change / prev_close * 100 if prev_close != 0 else 0.0

            result[ticker] = TickerSnapshot(
                ticker=ticker, name=ticker,
                price=price, prev_close=prev_close,
                day_change=change, day_change_pct=change_pct,
                currency="",
            )
        return result

    def _build_market_context(
        self, closes: pd.DataFrame, live: pd.DataFrame, fx_rates: dict
    ) -> dict:
        """Contexte marche : SPX/VIX depuis closes+live, commodities/FX en fetch separe."""
        ctx: dict = {}
        last_live  = live.iloc[-1]  if not live.empty   else None
        prev_daily = closes.iloc[-1] if len(closes) >= 1 else None
        prev2      = closes.iloc[-2] if len(closes) >= 2 else None

        # SPX + VIX : priorite au live intraday, fallback sur dernier daily
        for sym in [self.market_ticker, "^VIX"]:
            price = None
            # 1. Derniere valeur non-NaN dans le live (cherche en arriere)
            if not live.empty and sym in live.columns:
                vals = live[sym].dropna()
                if not vals.empty:
                    price = float(vals.iloc[-1])
            # 2. Fallback : dernier daily historique
            if price is None and prev_daily is not None and sym in prev_daily.index and not pd.isna(prev_daily[sym]):
                price = float(prev_daily[sym])
            if price is None:
                continue
            # Variation vs avant-derniere cloture daily
            if prev2 is not None and sym in prev2.index and not pd.isna(prev2[sym]):
                prev = float(prev2[sym])
                chg  = (price - prev) / prev * 100 if prev != 0 else 0.0
            else:
                chg = float("nan")
            ctx[sym] = {"price": price, "change_pct": chg}

        # Commodities + FX : fetch leger 5j independant
        extra_tickers = ["GC=F", "CL=F", "EURUSD=X", "EURCHF=X", "EURCAD=X"]
        key_map = {"EURUSD=X": "EURUSD", "EURCHF=X": "EURCHF", "EURCAD=X": "EURCAD",
                   "GC=F": "GC=F", "CL=F": "CL=F"}
        try:
            raw_extra = yf.download(
                " ".join(extra_tickers), period="5d",
                auto_adjust=True, progress=False,
            )
            if not raw_extra.empty:
                ec = raw_extra["Close"] if isinstance(raw_extra.columns, pd.MultiIndex) else raw_extra[["Close"]]
                if not isinstance(raw_extra.columns, pd.MultiIndex):
                    ec.columns = [extra_tickers[0]]
                ec = ec.dropna(how="all")
                for sym in extra_tickers:
                    if sym not in ec.columns:
                        continue
                    vals = ec[sym].dropna()
                    if len(vals) < 2:
                        continue
                    price = float(vals.iloc[-1])
                    prev  = float(vals.iloc[-2])
                    chg   = (price - prev) / prev * 100 if prev != 0 else 0.0
                    ctx[key_map.get(sym, sym)] = {"price": price, "change_pct": chg}
        except Exception as exc:
            logger.warning("Erreur fetch commodities/FX context : %s", exc)

        return ctx


    def _fetch_all_cpi_rates(self) -> dict:
        """
        Fetch inflation annuelle pour USD, EUR, CHF, CAD.
        Sources :
          - World Bank API  : donnees annuelles historiques (toutes devises)
          - BLS API         : CPI US mensuel, plus recent
          - ECB API         : HICP EUR mensuel, plus recent
        Cache 6h pour limiter les appels.
        """
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inflation_cache.json")

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                if time.time() - cached.get("_ts", 0) < self._CPI_CACHE_TTL:
                    cached.pop("_ts", None)
                    return {ccy: {int(k): v for k, v in yrs.items()}
                            for ccy, yrs in cached.items() if isinstance(yrs, dict)}
            except Exception:
                pass

        rates: dict = {"USD": {}, "EUR": {}, "CHF": {}, "CAD": {}}

        wb_map = {"USD": "US", "EUR": "EMU", "CHF": "CH", "CAD": "CA"}
        for ccy, iso in wb_map.items():
            try:
                url = (f"https://api.worldbank.org/v2/country/{iso}/indicator/"
                       f"FP.CPI.TOTL.ZG?format=json&mrv=5&per_page=5")
                req = urllib.request.Request(url, headers={"User-Agent": "PortfolioTracker/1.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read())
                for r in (data[1] or []):
                    if r.get("value") and r.get("date"):
                        rates[ccy][int(r["date"])] = round(r["value"] / 100.0, 4)
            except Exception as exc:
                logger.warning("World Bank %s : %s", ccy, exc)

        try:
            url = "https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0"
            req = urllib.request.Request(url, headers={"User-Agent": "PortfolioTracker/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            cpi_map = {}
            for d in data["Results"]["series"][0]["data"]:
                try:
                    k = (int(d["year"]), int(d["period"].replace("M", "")))
                    cpi_map[k] = float(d["value"])
                except (ValueError, TypeError):
                    pass
            yoy_by_year: dict = {}
            for (yr, mo), val in cpi_map.items():
                prev = cpi_map.get((yr - 1, mo))
                if prev and prev > 0:
                    yoy_by_year.setdefault(yr, []).append((val - prev) / prev)
            for yr, vals in yoy_by_year.items():
                rates["USD"][yr] = round(sum(vals) / len(vals), 4)
        except Exception as exc:
            logger.warning("BLS USD : %s", exc)

        try:
            ecb_url = ("https://data-api.ecb.europa.eu/service/data/ICP/"
                       "M.U2.N.000000.4.ANR?format=jsondata&startPeriod=2023-01")
            req = urllib.request.Request(ecb_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                ecb_data = json.loads(resp.read())
            obs = ecb_data["dataSets"][0]["series"]["0:0:0:0:0:0"]["observations"]
            periods = ecb_data["structure"]["dimensions"]["observation"][0]["values"]
            eu_yoy: dict = {}
            for idx, period_info in enumerate(periods):
                yr = int(period_info["id"][:4])
                val_list = obs.get(str(idx), [None])
                val = val_list[0]
                if val is not None and val != 0:
                    eu_yoy.setdefault(yr, []).append(float(val) / 100.0)
            for yr, vals in eu_yoy.items():
                rates["EUR"][yr] = round(sum(vals) / len(vals), 4)
        except Exception as exc:
            logger.warning("ECB EUR : %s", exc)

        fallback = {
            "USD": {2024: 0.0295, 2025: 0.0380, 2026: 0.0327},
            "EUR": {2024: 0.0226, 2025: 0.0247, 2026: 0.0230},
            "CHF": {2024: 0.0106, 2025: 0.0015, 2026: 0.0050},
            "CAD": {2024: 0.0238, 2025: 0.0207, 2026: 0.0220},
        }
        for ccy, fb in fallback.items():
            for yr, val in fb.items():
                if yr not in rates.get(ccy, {}):
                    rates.setdefault(ccy, {})[yr] = val

        try:
            to_cache = {ccy: {str(k): v for k, v in yrs.items()}
                        for ccy, yrs in rates.items()}
            to_cache["_ts"] = time.time()
            with open(cache_file, "w") as f:
                json.dump(to_cache, f, indent=2)
        except Exception:
            pass

        return rates


    def _fetch_fx_rates(self) -> dict[str, float]:
        """Telecharge les taux EUR/XXX courants."""
        try:
            raw = yf.download(
                " ".join(self._FX_PAIRS.values()),
                period="5d",
                auto_adjust=False,
                progress=False,
            )
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Close"]
            else:
                closes = raw[["Close"]]
                closes.columns = [list(self._FX_PAIRS.values())[0]]

            last = closes.dropna(how="all").iloc[-1]
            rates: dict[str, float] = {"EUR": 1.0}
            for currency, ticker in self._FX_PAIRS.items():
                val = last.get(ticker, None)
                rates[currency] = float(val) if val is not None and not pd.isna(val) else self._FX_FALLBACK[currency]
            return rates

        except Exception as exc:
            logger.warning("Erreur FX : %s - taux de repli utilises", exc)
            return dict(self._FX_FALLBACK)
