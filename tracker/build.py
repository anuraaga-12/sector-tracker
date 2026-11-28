"""Build the SQLite database from seed files + market-data files.

The database is a derived artefact: it can always be rebuilt with ``python -m tracker.build``.
The app calls :func:`ensure_database` on start-up and rebuilds only when an input changed.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

from . import analytics, config, db, marketcap, store
from .seed import load_taxonomy, load_universe


def _inputs() -> list[Path]:
    files = [config.ROOT / "settings.yaml"]
    for d in (config.TAXONOMY_DIR, config.UNIVERSE_DIR, config.MARKET, config.MANUAL):
        if d.exists():
            files += [p for p in d.rglob("*") if p.is_file()]
    return files


def needs_rebuild() -> bool:
    if not config.DB_PATH.exists():
        return True
    db_m = config.DB_PATH.stat().st_mtime
    return any(p.stat().st_mtime > db_m for p in _inputs())


def _classification_history(cls: pd.DataFrame) -> pd.DataFrame:
    """Diff the current mapping against the last recorded one and append changes."""
    snap_f = config.MARKET / "classification_snapshot.csv"
    hist_f = config.MARKET / "classification_history.csv"
    cur = cls[["nse_symbol", "subsector_id", "classification_type"]].copy()
    hist = store.read_table(hist_f)
    if snap_f.exists():
        prev = pd.read_csv(snap_f, dtype=str)
        m = prev.merge(cur, on=["nse_symbol", "subsector_id"], how="outer", suffixes=("_old", "_new"),
                       indicator="side")
        today = date.today().isoformat()
        ch = []
        for r in m.itertuples():
            if r.side == "left_only":
                ch.append((r.nse_symbol, r.subsector_id, r.classification_type_old, "removed", today))
            elif r.side == "right_only":
                ch.append((r.nse_symbol, r.subsector_id, r.classification_type_new, "added", today))
            elif r.classification_type_old != r.classification_type_new:
                ch.append((r.nse_symbol, r.subsector_id, f"{r.classification_type_old}->{r.classification_type_new}", "changed", today))
        if ch:
            new = pd.DataFrame(ch, columns=["nse_symbol", "subsector_id", "classification_type", "change", "changed_on"])
            hist = pd.concat([hist, new], ignore_index=True)
            store.write_table(hist, hist_f)
    store.write_table(cur, snap_f)
    return hist


def build(path: Path | None = None, log=print) -> dict:
    t0 = time.time()
    cfg = config.settings()
    target = Path(path or config.DB_PATH)
    tmp = target.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()

    tax = load_taxonomy()
    uni = load_universe(valid_subsectors=set(tax.subsectors["subsector_id"]))
    problems = tax.errors + uni.errors
    for p in problems:
        log(f"WARNING: {p}")

    close = store.read_wide(config.PRICES_FILE)
    bench = store.read_wide(config.BENCH_FILE)
    quotes = store.read_table(config.QUOTES_FILE)
    fund = store.read_table(config.FUND_FILE)
    if config.FUND_OVERRIDE.exists():
        ov = pd.read_csv(config.FUND_OVERRIDE)
        ov["source"] = ov.get("source", "Manual override")
        fund = pd.concat([fund[~fund["symbol"].isin(ov["symbol"])] if not fund.empty else fund, ov], ignore_index=True)

    last_close = close.ffill().iloc[-1] if not close.empty else None
    companies = marketcap.categorise(uni.companies, quotes, last_close)
    companies.insert(0, "company_id", range(1, len(companies) + 1))
    cid = companies.set_index("nse_symbol")["company_id"]

    cls = uni.classifications.copy()
    if config.MARKET.exists():
        hist = _classification_history(cls)
    else:
        hist = pd.DataFrame()

    con = sqlite3.connect(tmp)
    db.init_schema(con)
    tax.sectors.to_sql("sectors", con, if_exists="append", index=False)
    tax.subsectors.to_sql("subsectors", con, if_exists="append", index=False)
    companies.to_sql("companies", con, if_exists="append", index=False)
    cls_out = cls.assign(company_id=cls["nse_symbol"].map(cid)).drop(columns="nse_symbol")
    cls_out.to_sql("company_classification", con, if_exists="append", index=False)
    if not hist.empty:
        hist.to_sql("classification_history", con, if_exists="append", index=False)

    result = {"companies": len(companies), "classifications": len(cls), "problems": problems}
    if not close.empty:
        log(f"Computing analytics on {close.shape[1]} symbols × {close.shape[0]} days …")
        res = analytics.compute_all(close, bench, companies, uni.classifications, tax.subsectors, tax.sectors, cfg)
        sm = res["stock_metrics"]
        sm = sm[sm.index.isin(cid.index)]
        sm.insert(0, "company_id", sm.index.map(cid))
        sm.to_sql("stock_metrics", con, if_exists="append", index=False)
        gp = res["group_performance"]
        cols = [r[1] for r in con.execute("PRAGMA table_info(group_performance)")]
        gp[[c for c in cols if c in gp]].to_sql("group_performance", con, if_exists="append", index=False)
        res["index_series"].to_sql("index_series", con, if_exists="append", index=False)
        # reconstructed month-end snapshots + recorded ones
        snap = gp.rename(columns={"rank": "performance_rank"}).assign(
            breadth_score=gp["c_breadth"], snapshot_type="reconstructed")
        keep = ["calculation_date", "level", "entity_id", "performance_rank", "momentum_score", "breadth_score",
                "ew_1m", "ew_3m", "ew_6m", "pct_above_50dma", "snapshot_type"]
        snap[keep].to_sql("sector_snapshots", con, if_exists="append", index=False)
        rec = store.read_table(config.SNAPSHOT_FILE)
        if not rec.empty:
            rec = rec.assign(snapshot_type="recorded")
            rec[[c for c in keep if c in rec]].to_sql("sector_snapshots", con, if_exists="append", index=False)
        result["as_of"] = res["as_of"]
        # prices for the 52-week chart fallback are read from the file store directly
    if not fund.empty:
        f = fund.copy()
        f["company_id"] = f["symbol"].map(cid)
        f = f.dropna(subset=["company_id"])
        f = f.rename(columns={"revenue_cr": "revenue", "ebitda_cr": "ebitda", "pat_cr": "pat", "debt_cr": "debt",
                              "source": "source_reference"})
        f["reporting_period"] = f.get("reporting_period", "Latest (provider summary)")
        cols = [r[1] for r in con.execute("PRAGMA table_info(financial_metrics)")]
        f[[c for c in cols if c in f]].drop_duplicates(["company_id", "reporting_period"]).to_sql(
            "financial_metrics", con, if_exists="append", index=False)

    log_rows = [{"component": k, **v} for k, v in store.read_log().items()]
    seed_m = max(p.stat().st_mtime for p in list(config.TAXONOMY_DIR.glob("*")) + list(config.UNIVERSE_DIR.glob("*")))
    log_rows.append({"component": "classification_seed", "last_refresh": pd.Timestamp(seed_m, unit="s").isoformat(),
                     "status": "ok", "detail": "Seed files last modified"})
    log_rows.append({"component": "database_build", "last_refresh": store.now_iso(), "status": "ok",
                     "detail": json.dumps({k: v for k, v in result.items() if k != "problems"})})
    pd.DataFrame(log_rows).to_sql("refresh_log", con, if_exists="append", index=False)
    con.commit()
    con.close()
    os.replace(tmp, target)
    result["seconds"] = round(time.time() - t0, 1)
    log(f"Built {target} in {result['seconds']}s: {result}")
    return result


def ensure_database(log=lambda *a: None) -> None:
    if needs_rebuild():
        build(log=log)


if __name__ == "__main__":
    build(log=print)
    sys.exit(0)
