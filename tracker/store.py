"""File-backed market-data store (git-friendly compressed CSVs).

Prices are stored as a wide matrix (dates × symbols) of *adjusted* closes. This keeps the
repository small enough to be refreshed daily by a scheduled job and committed, so a free
host can serve the dashboard without hitting a market-data API on every page view.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_wide(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index.name = "date"
    return df.sort_index()


def write_wide(df: pd.DataFrame, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.sort_index().round(4)
    out.index = pd.to_datetime(out.index).strftime("%Y-%m-%d")
    out.index.name = "date"
    out.to_csv(path, compression="gzip" if str(path).endswith(".gz") else None)


def merge_prices(old: pd.DataFrame, new: pd.DataFrame, tol: float = 0.01) -> tuple[pd.DataFrame, list[str]]:
    """Merge an incremental download into history.

    Returns the merged frame and a list of symbols whose overlapping prices disagree by more
    than ``tol`` — a sign that a split / bonus / dividend changed the adjustment factor, so the
    full history for those symbols must be re-downloaded.
    """
    if old.empty:
        return new.sort_index(), []
    if new.empty:
        return old, []
    overlap = old.index.intersection(new.index)
    needs_full: list[str] = []
    for sym in new.columns.intersection(old.columns):
        a = old.loc[overlap, sym].dropna()
        b = new.loc[overlap, sym].reindex(a.index).dropna()
        if len(b) >= 2:
            ratio = (b / a.loc[b.index]).median()
            if np.isfinite(ratio) and abs(ratio - 1) > tol:
                needs_full.append(sym)
    merged = old.combine_first(new)
    merged.update(new)  # newer download wins on overlapping dates
    return merged.sort_index(), needs_full


def read_table(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"symbol": str}) if Path(path).exists() else pd.DataFrame()


def write_table(df: pd.DataFrame, path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def read_log() -> dict:
    if config.REFRESH_LOG.exists():
        return json.loads(config.REFRESH_LOG.read_text())
    return {}


def write_log(component: str, status: str, detail: str = "") -> None:
    log = read_log()
    log[component] = {"last_refresh": now_iso(), "status": status, "detail": detail}
    config.REFRESH_LOG.parent.mkdir(parents=True, exist_ok=True)
    config.REFRESH_LOG.write_text(json.dumps(log, indent=2))
