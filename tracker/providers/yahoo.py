"""Yahoo Finance adapter (via the unofficial `yfinance` library).

Yahoo is free but unofficial: it rate-limits aggressively, especially from cloud IPs, and
field definitions can change. Everything here is defensive — failures return empty results
and are surfaced on the Data Quality page rather than crashing the app. For production use,
swap in a licensed feed implementing the same functions.
"""
from __future__ import annotations

import time
from typing import Iterable

import numpy as np
import pandas as pd

from .. import config

CRORE = 1e7


def _yf():
    import yfinance as yf  # imported lazily so the engine runs without it
    return yf


def _close_frame(data: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    if data is None or data.empty:
        return pd.DataFrame()
    if isinstance(data.columns, pd.MultiIndex):
        lvl0 = data.columns.get_level_values(0)
        if "Close" in lvl0:
            close = data["Close"]
        else:  # group_by="ticker" layout
            close = data.xs("Close", axis=1, level=1)
    else:
        close = data[["Close"]].rename(columns={"Close": tickers[0]})
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close.dropna(how="all")


def download_close(tickers: Iterable[str], start: str | None = None, period: str | None = None,
                   chunk: int | None = None, pause: float | None = None, log=print) -> pd.DataFrame:
    s = config.settings()["data"]
    chunk = chunk or s["download_chunk"]
    pause = s["download_pause_sec"] if pause is None else pause
    tickers = list(dict.fromkeys(tickers))
    frames = []
    yf = _yf()
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        for attempt in range(3):
            try:
                data = yf.download(batch, start=start, period=None if start else (period or "max"),
                                   auto_adjust=True, progress=False, threads=True, group_by="column")
                frames.append(_close_frame(data, batch))
                break
            except Exception as exc:  # rate limit / network
                log(f"  batch {i // chunk + 1}: attempt {attempt + 1} failed: {exc}")
                time.sleep(pause * (attempt + 2) * 5)
        log(f"  downloaded {min(i + chunk, len(tickers))}/{len(tickers)}")
        time.sleep(pause)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    return out.sort_index()


def download_ohlcv(ticker: str, period: str = "5y", interval: str = "1d") -> pd.DataFrame:
    try:
        df = _yf().Ticker(ticker).history(period=period, interval=interval, auto_adjust=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    keep = [c for c in ["Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in df]
    return df[keep]


def _get(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None and not (isinstance(v, float) and np.isnan(v)):
            return v
    return None


def fetch_quote(ticker: str) -> dict:
    """Market cap / shares (fast_info) and summary ratios (info). Values in ₹ crore."""
    out: dict = {}
    try:
        t = _yf().Ticker(ticker)
        fi = t.fast_info
        mc = getattr(fi, "market_cap", None)
        sh = getattr(fi, "shares", None)
        out["market_cap_cr"] = mc / CRORE if mc else None
        out["shares"] = sh
    except Exception:
        t = None
    return out


def fetch_fundamentals(ticker: str) -> dict:
    """Summary fundamentals. Yahoo's 'info' block mixes TTM and latest-quarter figures."""
    try:
        t = _yf().Ticker(ticker)
        info = t.info or {}
    except Exception:
        return {}
    rev = _get(info, "totalRevenue")
    ebitda = _get(info, "ebitda")
    pat = _get(info, "netIncomeToCommon")
    debt = _get(info, "totalDebt")
    de = _get(info, "debtToEquity")
    out = {
        "revenue_cr": rev / CRORE if rev else None,
        "revenue_growth": _get(info, "revenueGrowth"),
        "ebitda_cr": ebitda / CRORE if ebitda else None,
        "ebitda_margin": _get(info, "ebitdaMargins"),
        "pat_cr": pat / CRORE if pat else None,
        "pat_growth": _get(info, "earningsGrowth", "earningsQuarterlyGrowth"),
        "roe": _get(info, "returnOnEquity"),
        "debt_cr": debt / CRORE if debt else None,
        "debt_to_equity": de / 100 if de is not None else None,  # Yahoo reports D/E in %
        "pe": _get(info, "trailingPE"),
        "pb": _get(info, "priceToBook"),
        "ev_ebitda": _get(info, "enterpriseToEbitda"),
        "dividend_yield": _get(info, "dividendYield"),
        "shares": _get(info, "sharesOutstanding"),
        "market_cap_cr": (_get(info, "marketCap") or 0) / CRORE or None,
    }
    # ROCE = EBIT / (Total assets - Current liabilities), latest annual statements
    try:
        inc, bs = t.income_stmt, t.balance_sheet
        ebit = inc.loc["EBIT"].iloc[0]
        ce = bs.loc["Total Assets"].iloc[0] - bs.loc["Current Liabilities"].iloc[0]
        out["roce"] = float(ebit / ce) if ce else None
        out["roce_period"] = str(pd.to_datetime(inc.columns[0]).date())
    except Exception:
        out["roce"] = None
    return out


def fetch_statements(ticker: str) -> dict:
    """Annual and quarterly income statements for charts (₹ crore)."""
    res = {}
    try:
        t = _yf().Ticker(ticker)
        for name, df in (("annual", t.income_stmt), ("quarterly", t.quarterly_income_stmt)):
            if df is None or df.empty:
                continue
            rows = {k: v for k, v in {
                "Revenue": "Total Revenue", "Operating Income": "Operating Income",
                "EBITDA": "EBITDA", "Net Income": "Net Income"}.items() if v in df.index}
            sub = df.loc[list(rows.values())].T / CRORE
            sub.columns = list(rows.keys())
            sub.index = pd.to_datetime(sub.index)
            res[name] = sub.sort_index()
    except Exception:
        pass
    return res
