"""Data refresh CLI.

    python -m tracker.refresh prices            # incremental price update (full on first run)
    python -m tracker.refresh prices --full     # re-download full history
    python -m tracker.refresh quotes            # market cap / shares
    python -m tracker.refresh fundamentals [--limit 100] [--stale-days 30]
    python -m tracker.refresh snapshot          # record today's rankings (rotation history)
    python -m tracker.refresh daily             # prices + quotes + build + snapshot
    python -m tracker.refresh weekly            # daily + fundamentals for stale names
    python -m tracker.refresh amfi FILE.xlsx    # import AMFI categorisation file
    python -m tracker.refresh import-prices FILE.csv   # manual long-format prices (symbol,date,close)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

import pandas as pd

from . import build as builder
from . import config, store
from .seed import load_taxonomy, load_universe


def _symbols() -> list[str]:
    tax = load_taxonomy()
    uni = load_universe(valid_subsectors=set(tax.subsectors["subsector_id"]))
    return uni.companies["nse_symbol"].tolist()


def _bench_tickers() -> list[str]:
    cfg = config.settings()["benchmarks"]
    tax = load_taxonomy()
    t = {cfg["nifty50"], cfg["nifty500"], *filter(None, tax.sectors["benchmark"].tolist()),
         *(cfg.get("sector_overrides") or {}).values()}
    return sorted(t)


def refresh_prices(full: bool = False, symbols: list[str] | None = None, log=print) -> None:
    from .providers import yahoo
    years = config.settings()["data"]["history_years"]
    syms = symbols or _symbols()
    tick = {config.yahoo_ticker(s): s for s in syms}
    old = store.read_wide(config.PRICES_FILE)
    oldb = store.read_wide(config.BENCH_FILE)
    start_full = (date.today() - timedelta(days=int(365.25 * years) + 10)).isoformat()
    if full or old.empty:
        start = start_full
    else:
        start = (old.index.max() - pd.Timedelta(days=14)).date().isoformat()
    log(f"Downloading {len(tick)} stocks from {start} …")
    new = yahoo.download_close(list(tick), start=start, log=log).rename(columns=tick)
    # names never downloaded before need their full history
    missing_hist = [s for s in syms if s not in old.columns and s in new.columns] if not old.empty else []
    merged, needs_full = store.merge_prices(old, new) if not full else (new, [])
    refetch = sorted(set(needs_full) | set(missing_hist))
    if refetch and not full:
        log(f"Re-downloading full history for {len(refetch)} symbols (new names or adjustment changes) …")
        fullp = yahoo.download_close([config.yahoo_ticker(s) for s in refetch], start=start_full, log=log)
        fullp = fullp.rename(columns={config.yahoo_ticker(s): s for s in refetch})
        merged = merged.drop(columns=[c for c in refetch if c in merged.columns]).join(fullp, how="outer")
    cutoff = pd.Timestamp(start_full)
    merged = merged[merged.index >= cutoff]
    store.write_wide(merged, config.PRICES_FILE)
    nb = yahoo.download_close(_bench_tickers(), start=start if not oldb.empty else start_full, log=log)
    mb, _ = store.merge_prices(oldb, nb)
    store.write_wide(mb[mb.index >= cutoff], config.BENCH_FILE)
    got = int(new.notna().any().sum())
    store.write_log("prices", "ok" if got else "error", f"{got}/{len(syms)} symbols returned data; last date {merged.index.max().date() if not merged.empty else 'n/a'}")
    log(f"Prices: {got}/{len(syms)} symbols updated.")


def refresh_quotes(symbols: list[str] | None = None, log=print) -> None:
    from .providers import yahoo
    syms = symbols or _symbols()
    rows = []
    for i, s in enumerate(syms, 1):
        q = yahoo.fetch_quote(config.yahoo_ticker(s))
        rows.append({"symbol": s, **q, "as_of": date.today().isoformat(), "source": "Yahoo Finance fast_info"})
        if i % 50 == 0:
            log(f"  quotes {i}/{len(syms)}")
    df = pd.DataFrame(rows)
    for c in ("market_cap_cr", "shares"):  # float, so NaN / carried-over values fit (pandas 3 is strict)
        df[c] = pd.to_numeric(df.get(c), errors="coerce").astype(float)
    old = store.read_table(config.QUOTES_FILE)
    if not old.empty:  # keep last good value where today's fetch failed
        df = df.set_index("symbol")
        old = old.set_index("symbol")
        bad = df["market_cap_cr"].isna() & df.index.isin(old.index)
        if bad.any():
            prev = old.loc[df.index[bad]]
            for c in ("market_cap_cr", "shares", "as_of", "source"):
                if c in prev:
                    df.loc[bad, c] = prev[c].astype(df[c].dtype) if c in ("market_cap_cr", "shares") else prev[c].astype(str)
        df = df.reset_index()
    store.write_table(df, config.QUOTES_FILE)
    ok = int(df["market_cap_cr"].notna().sum())
    store.write_log("market_cap", "ok" if ok else "error", f"{ok}/{len(syms)} market caps")
    log(f"Quotes: {ok}/{len(syms)} market caps.")


def refresh_fundamentals(limit: int | None = None, stale_days: int = 30, log=print) -> None:
    from .providers import yahoo
    import time
    syms = _symbols()
    old = store.read_table(config.FUND_FILE)
    if not old.empty:
        age = (pd.Timestamp.today() - pd.to_datetime(old.set_index("symbol")["as_of"])).dt.days
        fresh = set(age[age < stale_days].index)
        syms = [s for s in syms if s not in fresh]
    if limit:
        syms = syms[:limit]
    rows = []
    for i, s in enumerate(syms, 1):
        f = yahoo.fetch_fundamentals(config.yahoo_ticker(s))
        if f:
            rows.append({"symbol": s, "reporting_period": "Latest (Yahoo summary: TTM; growth = latest qtr YoY)",
                         **f, "source": "Yahoo Finance via yfinance (unofficial)", "as_of": date.today().isoformat()})
        time.sleep(0.5)
        if i % 25 == 0:
            log(f"  fundamentals {i}/{len(syms)}")
    new = pd.DataFrame(rows)
    out = pd.concat([old[~old["symbol"].isin(new.get("symbol", []))] if not old.empty else old, new], ignore_index=True)
    store.write_table(out, config.FUND_FILE)
    store.write_log("fundamentals", "ok" if rows else "error", f"{len(rows)} refreshed this run; {len(out)} on file")
    log(f"Fundamentals: refreshed {len(rows)}.")


def record_snapshot(log=print) -> None:
    """Append today's latest rankings to snapshots.csv so rotation history reflects what the
    tracker actually showed at the time (incl. the classification in force then)."""
    from . import db
    df = db.read_sql("""SELECT calculation_date, level, entity_id, rank AS performance_rank, momentum_score,
                        c_breadth AS breadth_score, ew_1m, ew_3m, ew_6m, pct_above_50dma
                        FROM group_performance WHERE calculation_date = (SELECT MAX(calculation_date) FROM group_performance)""")
    if df.empty:
        log("No performance data — run prices first.")
        return
    old = store.read_table(config.SNAPSHOT_FILE)
    out = pd.concat([old, df], ignore_index=True).drop_duplicates(["calculation_date", "level", "entity_id"], keep="last")
    store.write_table(out, config.SNAPSHOT_FILE)
    log(f"Recorded snapshot for {df['calculation_date'].iloc[0]} ({len(df)} rows).")


def import_amfi(path: str, log=print) -> None:
    """Convert AMFI's xlsx into data/manual/amfi_categorisation.csv (isin, nse_symbol, category, as_of)."""
    raw = pd.read_excel(path, header=None)
    hdr = raw.index[raw.apply(lambda r: r.astype(str).str.contains("ISIN", case=False).any(), axis=1)][0]
    df = pd.read_excel(path, header=hdr)
    cols = {c: str(c).lower() for c in df.columns}
    df = df.rename(columns=cols)
    isin = next(c for c in df.columns if "isin" in c)
    sym = next((c for c in df.columns if "nse symbol" in c or c == "symbol"), None)
    cat = next(c for c in df.columns if "categor" in c)
    out = pd.DataFrame({"isin": df[isin], "nse_symbol": df[sym] if sym else "", "category": df[cat],
                        "as_of": pd.Timestamp.today().date().isoformat()})
    config.MANUAL.mkdir(parents=True, exist_ok=True)
    out.dropna(subset=["category"]).to_csv(config.AMFI_FILE, index=False)
    store.write_log("amfi", "ok", f"{len(out)} rows from {path}")
    log(f"AMFI categorisation imported: {len(out)} rows → {config.AMFI_FILE}")


def import_prices(path: str, log=print) -> None:
    """Manual fallback: long CSV with columns symbol,date,close (adjusted)."""
    df = pd.read_csv(path, parse_dates=["date"])
    wide = df.pivot_table(index="date", columns="symbol", values="close")
    merged, _ = store.merge_prices(store.read_wide(config.PRICES_FILE), wide)
    store.write_wide(merged, config.PRICES_FILE)
    store.write_log("prices", "ok", f"manual import from {path}")
    log(f"Imported {wide.shape[1]} symbols × {wide.shape[0]} dates.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task", choices=["prices", "quotes", "fundamentals", "snapshot", "daily", "weekly",
                                     "build", "amfi", "import-prices"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--stale-days", type=int, default=30)
    a = ap.parse_args(argv)
    if a.task == "prices":
        refresh_prices(full=a.full)
    elif a.task == "quotes":
        refresh_quotes()
    elif a.task == "fundamentals":
        refresh_fundamentals(a.limit, a.stale_days)
    elif a.task == "amfi":
        import_amfi(a.file)
    elif a.task == "import-prices":
        import_prices(a.file)
    elif a.task in ("daily", "weekly"):
        refresh_prices(full=a.full)
        if a.task == "weekly" or not config.QUOTES_FILE.exists():
            refresh_quotes()          # shares outstanding; market cap = shares × daily close
        if a.task == "weekly":
            refresh_fundamentals(a.limit, a.stale_days)
        builder.build()
        record_snapshot()
    if a.task in ("prices", "quotes", "fundamentals", "amfi", "import-prices", "build"):
        builder.build()
    if a.task == "snapshot":
        builder.ensure_database()
        record_snapshot()
    return 0


if __name__ == "__main__":
    sys.exit(main())
