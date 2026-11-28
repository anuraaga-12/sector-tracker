"""Mutual-fund data: daily NAVs and monthly portfolio holdings (free, public, no API key).

* NAV history  — mfapi.in, a free mirror of AMFI's daily NAV file, keyed by AMFI scheme code.
* Holdings     — the open ``fund-holdings-data`` archive (github.com/kushagra-agarwal-a/fund-holdings-data),
                 which parses each fund house's SEBI-mandated monthly portfolio disclosure (the AMC's own
                 Excel file) into one JSON per portfolio. Funds disclose within ~10 days of month-end.
* ISIN → NSE symbol and size bucket — NSE's EQUITY_L list and the Nifty 100 / Midcap 150 constituent files.

Every function returns an empty result on failure so a source outage never breaks the daily refresh.
"""
from __future__ import annotations

import io
import json
import urllib.request

import pandas as pd

from . import nse

NAV_URL = "https://api.mfapi.in/mf/{code}"
HOLDINGS_BASE = "https://raw.githubusercontent.com/kushagra-agarwal-a/fund-holdings-data/main"
EQUITY_LIST_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY100_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
MIDCAP150_URL = "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv"
_HEADERS = {"User-Agent": "india-sector-tracker/1.0 (+https://github.com/anuraaga-12/sector-tracker)"}


def _get(url: str, timeout: int = 60) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=_HEADERS), timeout=timeout,
                                    context=nse._ssl_context()) as r:
            return r.read()
    except Exception:
        return None


def _json(url: str, timeout: int = 60):
    raw = _get(url, timeout)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


# ----------------------------------------------------------------------------- NAV
def nav_history(code: int | str) -> tuple[dict, pd.Series]:
    """(scheme meta, NAV series indexed by date) for one AMFI scheme code."""
    d = _json(NAV_URL.format(code=code))
    if not d or not d.get("data"):
        return {}, pd.Series(dtype=float)
    df = pd.DataFrame(d["data"])
    s = pd.Series(pd.to_numeric(df["nav"], errors="coerce").values,
                  index=pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce"), name=str(code))
    s = s[s.index.notna() & (s > 0)].sort_index()
    return d.get("meta") or {}, s[~s.index.duplicated(keep="last")]


# ----------------------------------------------------------------------------- holdings
def monthly_filings() -> list[str]:
    """Month-end disclosure dates available in the archive, newest first (e.g. ['2026-10-31', ...])."""
    d = _json(f"{HOLDINGS_BASE}/catalog/filings.json")
    if not d:
        return []
    return sorted({f["as_of"] for f in d.get("filings", []) if f.get("cadence") == "monthly"}, reverse=True)


def catalogue() -> dict:
    """AMFI scheme code → {portfolio_id, available_as_of, ...}. All plans of a scheme share one portfolio.
    About 9 MB, so the refresh only downloads it when a disclosure it doesn't have yet may be available."""
    return _json(f"{HOLDINGS_BASE}/catalog/amfi-lookup.json", timeout=120) or {}


def portfolio(as_of: str, portfolio_id: str) -> pd.DataFrame:
    """Holdings rows of one disclosure: holding_type, instrument, isin, industry, quantity,
    value_cr, pct_nav (percent). Empty if the fund has not filed for that month."""
    d = _json(f"{HOLDINGS_BASE}/portfolios/asof/{as_of}/{portfolio_id}.json")
    if not d or not d.get("holdings"):
        return pd.DataFrame()
    df = pd.DataFrame(d["holdings"])
    unit = (d.get("meta") or {}).get("market_value_unit", "INR_LAKH")
    scale = {"INR_LAKH": 0.01, "INR_CRORE": 1.0, "INR": 1e-7}.get(unit, 0.01)
    out = pd.DataFrame({
        "holding_type": df.get("holding_type"), "instrument": df.get("instrument"), "isin": df.get("isin"),
        "industry": df.get("industry"), "section": df.get("section"),
        "quantity": pd.to_numeric(df.get("quantity"), errors="coerce"),
        "value_cr": pd.to_numeric(df.get("market_value"), errors="coerce") * scale,
        "pct_nav": pd.to_numeric(df.get("pct_nav"), errors="coerce"),
    })
    return out


# ----------------------------------------------------------------------------- reference lists
def isin_reference() -> pd.DataFrame:
    """isin, symbol, company, size (Large = Nifty 100, Mid = Nifty Midcap 150, Small = other listed)."""
    raw = nse._get(EQUITY_LIST_URL, timeout=60)
    if not raw:
        return pd.DataFrame()
    try:
        eq = pd.read_csv(io.BytesIO(raw))
        eq.columns = [str(c).strip().lower() for c in eq.columns]
        out = pd.DataFrame({"isin": eq["isin number"].astype(str).str.strip(), "symbol": eq["symbol"].astype(str).str.strip(),
                            "company": eq["name of company"].astype(str).str.strip()})
    except Exception:
        return pd.DataFrame()
    size = pd.Series("Small", index=out.index)
    for url, lab in ((MIDCAP150_URL, "Mid"), (NIFTY100_URL, "Large")):
        raw = nse._get(url)
        if not raw:
            return pd.DataFrame()  # without both lists the size split would be wrong — keep the previous file
        try:
            lst = pd.read_csv(io.BytesIO(raw))
            isins = set(lst[[c for c in lst.columns if "ISIN" in c][0]].astype(str).str.strip())
        except Exception:
            return pd.DataFrame()
        size[out["isin"].isin(isins)] = lab
    out["size"] = size
    return out.drop_duplicates("isin")
