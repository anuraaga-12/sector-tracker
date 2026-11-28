"""Generate a SYNTHETIC market-data sandbox for offline demos and tests.

    TRACKER_DATA_MODE=demo python -m tracker.demo

Prices follow random walks with sector / sub-sector factors so rankings, breadth and
rotation views have something to show. None of these numbers are real; the UI displays a
prominent banner whenever demo mode is active.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, store
from .seed import load_taxonomy, load_universe


def generate(days: int = 1400, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    tax = load_taxonomy()
    uni = load_universe(valid_subsectors=set(tax.subsectors["subsector_id"]))
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=days)
    mkt = rng.normal(0.0004, 0.009, days)
    sec_f = {s: rng.normal(0.0001, 0.006, days) + np.sin(np.linspace(0, rng.uniform(2, 8), days)) * 0.0015
             for s in tax.sectors["sector_id"]}
    sub_sec = tax.subsectors.set_index("subsector_id")["sector_id"]
    sub_f = {s: rng.normal(0, 0.005, days) + np.cos(np.linspace(0, rng.uniform(2, 10), days)) * 0.0012
             for s in tax.subsectors["subsector_id"]}
    prim = uni.classifications[uni.classifications["classification_type"] == "primary"].set_index("nse_symbol")["subsector_id"]
    cols = {}
    for sym in uni.companies["nse_symbol"]:
        sub = prim.get(sym)
        sec = sub_sec.get(sub)
        beta = rng.uniform(0.7, 1.4)
        r = beta * mkt + sec_f.get(sec, 0) + sub_f.get(sub, 0) + rng.normal(0, 0.016, days)
        p = 100 * rng.uniform(0.5, 30) * np.exp(np.cumsum(r))
        listed = rng.random() < 0.08  # some recent listings
        if listed:
            p[: rng.integers(200, days - 100)] = np.nan
        cols[sym] = p
    close = pd.DataFrame(cols, index=dates)
    # a couple of deliberately stale / missing names to exercise the data-quality page
    stale = list(close.columns[:2])
    close.loc[close.index[-15]:, stale] = np.nan
    close = close.drop(columns=list(close.columns[2:4]))
    n500 = 100 * np.exp(np.cumsum(mkt + rng.normal(0, 0.002, days)))
    bench = pd.DataFrame({"^CRSLDX": n500 * 200, "^NSEI": n500 * 230})
    for b in tax.sectors["benchmark"].dropna().unique():
        if b not in bench:
            sec = tax.sectors.loc[tax.sectors["benchmark"] == b, "sector_id"].iloc[0]
            bench[b] = 100 * np.exp(np.cumsum(mkt + sec_f[sec]))
    bench.index = dates
    store.write_wide(close, config.PRICES_FILE)
    store.write_wide(bench, config.BENCH_FILE)
    mcap = np.exp(rng.normal(np.log(15000), 1.6, len(uni.companies)))
    q = pd.DataFrame({"symbol": uni.companies["nse_symbol"], "market_cap_cr": mcap.round(0)})
    last = close.ffill().iloc[-1].reindex(q["symbol"]).values
    q["shares"] = q["market_cap_cr"] * 1e7 / last
    q["as_of"] = dates[-1].date().isoformat()
    q["source"] = "SYNTHETIC DEMO"
    store.write_table(q, config.QUOTES_FILE)
    f = pd.DataFrame({
        "symbol": uni.companies["nse_symbol"], "reporting_period": "SYNTHETIC",
        "revenue_cr": (mcap / rng.uniform(1, 8, len(mcap))).round(0),
        "revenue_growth": rng.normal(0.12, 0.1, len(mcap)).round(3),
        "ebitda_margin": rng.uniform(0.05, 0.35, len(mcap)).round(3),
        "pat_growth": rng.normal(0.15, 0.2, len(mcap)).round(3),
        "roce": rng.uniform(0.05, 0.4, len(mcap)).round(3), "roe": rng.uniform(0.05, 0.3, len(mcap)).round(3),
        "debt_to_equity": rng.uniform(0, 1.5, len(mcap)).round(2), "pe": rng.uniform(10, 80, len(mcap)).round(1),
        "pb": rng.uniform(1, 12, len(mcap)).round(1), "source": "SYNTHETIC DEMO", "as_of": dates[-1].date().isoformat(),
    })
    store.write_table(f.sample(frac=0.9, random_state=1), config.FUND_FILE)
    for c in ("prices", "market_cap", "fundamentals"):
        store.write_log(c, "ok", "SYNTHETIC DEMO DATA")
    print(f"Synthetic demo data written to {config.MARKET}")


if __name__ == "__main__":
    if config.DATA_MODE != "demo":
        raise SystemExit("Refusing to write synthetic data outside demo mode. Set TRACKER_DATA_MODE=demo.")
    generate()
