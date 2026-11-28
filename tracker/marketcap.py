"""Market-cap calculation and categorisation (AMFI first, indicative thresholds as fallback)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def load_amfi() -> pd.DataFrame:
    """Optional user-supplied AMFI list: columns nse_symbol and/or isin, category, as_of.

    Download AMFI's half-yearly 'Average market capitalisation' file from amfiindia.com and
    convert with ``python -m tracker.refresh amfi <file.xlsx>``."""
    if not config.AMFI_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(config.AMFI_FILE, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def categorise(companies: pd.DataFrame, quotes: pd.DataFrame, last_close: pd.Series | None = None) -> pd.DataFrame:
    """Attach market_cap_cr / category / source / as_of to the company frame."""
    cfg = config.settings()["market_cap"]
    out = companies.copy()
    q = quotes.set_index("symbol") if not quotes.empty else pd.DataFrame()
    mc = q["market_cap_cr"].astype(float) if "market_cap_cr" in q else pd.Series(dtype=float)
    as_of = q["as_of"].astype(str) if "as_of" in q else pd.Series(dtype=str)
    # Prefer shares (refreshed weekly) × latest close (refreshed daily) so market cap stays current
    if last_close is not None and "shares" in q:
        fresh = q["shares"].astype(float) * last_close.reindex(q.index) / 1e7
        price_date = getattr(last_close, "name", None)
        mc = fresh.combine_first(mc.reindex(q.index))
        if price_date is not None:
            as_of = as_of.reindex(q.index).where(fresh.isna(), str(pd.Timestamp(price_date).date()))
    out["market_cap_cr"] = out["nse_symbol"].map(mc)
    out["market_cap_as_of"] = out["nse_symbol"].map(as_of)

    amfi = load_amfi()
    cat = pd.Series(index=out.index, dtype=object)
    src = pd.Series(index=out.index, dtype=object)
    if not amfi.empty and "category" in amfi:
        amfi["category"] = amfi["category"].str.strip().str.title().str.replace(" Cap", "", regex=False)
        label = f"AMFI ({amfi['as_of'].iloc[0]})" if "as_of" in amfi else "AMFI"
        by_sym = amfi.set_index("nse_symbol")["category"] if "nse_symbol" in amfi else pd.Series(dtype=str)
        by_isin = amfi.set_index("isin")["category"] if "isin" in amfi else pd.Series(dtype=str)
        a = out["nse_symbol"].map(by_sym)
        if "isin" in out:
            a = a.fillna(out["isin"].map(by_isin))
        cat[a.notna()] = a[a.notna()]
        src[a.notna()] = label
    m = out["market_cap_cr"]
    need = cat.isna() & m.notna()
    ind = np.select([m >= cfg["large_min_cr"], m >= cfg["mid_min_cr"]], ["Large", "Mid"], default="Small")
    cat[need] = pd.Series(ind, index=out.index)[need]
    src[need] = "Indicative threshold (settings.yaml) — not official AMFI"
    # Micro is a sub-bucket of Small (not an AMFI category)
    micro = (cat == "Small") & (m < cfg["micro_max_cr"])
    cat[micro] = "Micro"
    src[micro] = src[micro].fillna("") + " · Micro = Small below ₹" + f"{cfg['micro_max_cr']:,} cr (indicative)"
    out["market_cap_category"] = cat
    out["market_cap_category_source"] = src
    return out
