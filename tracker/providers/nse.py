"""NSE's official end-of-day files (free, public archive — no login or API key).

Yahoo often posts the day's closing price for NSE stocks and indices late, sometimes not
until the next day. NSE publishes its bhavcopy (closing price of every listed security) and
the closing value of every index each evening, so the refresh uses these to fill the most
recent days that Yahoo is still missing.

These are unadjusted closes. For the latest few days that equals the adjusted close, and the
next Yahoo download overwrites them anyway (and re-downloads full history if a split or
dividend changed the adjustment). Every failure returns an empty result.
"""
from __future__ import annotations

import io
import ssl
import urllib.request
import zipfile
from datetime import date

import pandas as pd

BHAV_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"
INDEX_URL = "https://nsearchives.nseindia.com/content/indices/ind_close_all_{d:%d%m%Y}.csv"
# NSE's archive rejects requests without a browser-like User-Agent.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept": "*/*"}
# Equity series, most preferred first (EQ = normal, BE/BZ = trade-for-trade, IV = InvITs, SM/ST = SME).
EQUITY_SERIES = ["EQ", "BE", "BZ", "BL", "IV", "RR", "SM", "ST"]


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without system CA certificates; certifi (installed with
    # requests / yfinance) provides them. Verification always stays on.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _get(url: str, timeout: int = 30) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=timeout,
                                    context=_ssl_context()) as r:
            return r.read()
    except Exception:  # 404 = holiday / not published yet; anything else = blocked or offline
        return None


def stock_closes(d: date) -> pd.Series:
    """Closing price by NSE symbol for trading day ``d`` (empty if not published / holiday)."""
    raw = _get(BHAV_URL.format(d=d))
    if not raw:
        return pd.Series(dtype=float)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
        df = df[df["SctySrs"].isin(EQUITY_SERIES)].copy()
        df["_o"] = df["SctySrs"].map({s: i for i, s in enumerate(EQUITY_SERIES)})
        df = df.sort_values("_o").drop_duplicates("TckrSymb")
        s = pd.to_numeric(df.set_index("TckrSymb")["ClsPric"], errors="coerce")
        return s[s > 0].astype(float)
    except Exception:
        return pd.Series(dtype=float)


def index_closes(d: date) -> pd.Series:
    """Closing value by lower-cased NSE index name (e.g. 'nifty 500') for trading day ``d``."""
    raw = _get(INDEX_URL.format(d=d))
    if not raw:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [str(c).strip() for c in df.columns]
        s = pd.to_numeric(df.set_index(df["Index Name"].astype(str).str.strip().str.lower())["Closing Index Value"],
                          errors="coerce")
        return s[s > 0].astype(float)
    except Exception:
        return pd.Series(dtype=float)
