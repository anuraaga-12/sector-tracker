"""Paths and settings."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = DATA / "seed"
TAXONOMY_DIR = SEED / "taxonomy"
UNIVERSE_DIR = SEED / "universe"
MANUAL = DATA / "manual"

# DATA_MODE=demo switches every market-data file to a synthetic sandbox so the UI can be
# explored (and tested) without network access. The UI shows a loud banner in demo mode.
DATA_MODE = os.environ.get("TRACKER_DATA_MODE", "live").lower()
MARKET = DATA / ("demo_market" if DATA_MODE == "demo" else "market")
DB_PATH = Path(os.environ.get("TRACKER_DB", DATA / ("demo.db" if DATA_MODE == "demo" else "tracker.db")))

PRICES_FILE = MARKET / "prices_close.csv.gz"
BENCH_FILE = MARKET / "benchmarks_close.csv.gz"
QUOTES_FILE = MARKET / "quotes.csv"
FUND_FILE = MARKET / "fundamentals.csv"
SNAPSHOT_FILE = MARKET / "snapshots.csv"
REFRESH_LOG = MARKET / "refresh_log.json"
AMFI_FILE = MANUAL / "amfi_categorisation.csv"      # optional, user-supplied
FUND_OVERRIDE = MANUAL / "fundamentals_override.csv"  # optional, user-supplied
COMPANY_OVERRIDE = MANUAL / "company_master_override.csv"  # optional ISIN / BSE code / status
VERIFICATION_FILE = MANUAL / "classification_verification.csv"  # optional: evidence after checking filings


@lru_cache(maxsize=1)
def settings() -> dict:
    with open(ROOT / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def yahoo_ticker(symbol: str) -> str:
    return f"{symbol}{settings()['data']['yahoo_suffix']}"
