"""SQLite schema and connection helpers."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from . import config

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sectors (
    sector_id      TEXT PRIMARY KEY,
    sector_name    TEXT NOT NULL,
    priority       INTEGER,
    benchmark      TEXT,
    description    TEXT,
    value_chain    TEXT
);

CREATE TABLE IF NOT EXISTS subsectors (
    subsector_id          TEXT PRIMARY KEY,
    sector_id             TEXT NOT NULL REFERENCES sectors(sector_id),
    subsector_name        TEXT NOT NULL,
    description           TEXT,
    value_chain_position  TEXT,
    profile_json          TEXT          -- customers, inputs, economics, drivers, risks, ratings…
);
CREATE INDEX IF NOT EXISTS ix_subsectors_sector ON subsectors(sector_id);

CREATE TABLE IF NOT EXISTS companies (
    company_id                 INTEGER PRIMARY KEY,
    company_name               TEXT NOT NULL,
    nse_symbol                 TEXT NOT NULL UNIQUE,
    bse_code                   TEXT,
    isin                       TEXT,
    listing_status             TEXT NOT NULL DEFAULT 'Mainboard',
    business_model             TEXT,
    market_position            TEXT,
    primary_business           TEXT,
    customer_industry          TEXT,
    market_cap_cr              REAL,          -- ₹ crore
    market_cap_category        TEXT,          -- Large / Mid / Small / Micro
    market_cap_category_source TEXT,          -- 'AMFI <date>' or 'Indicative threshold'
    market_cap_as_of           TEXT
);
CREATE INDEX IF NOT EXISTS ix_companies_isin ON companies(isin);

CREATE TABLE IF NOT EXISTS company_classification (
    company_id                INTEGER NOT NULL REFERENCES companies(company_id),
    subsector_id              TEXT NOT NULL REFERENCES subsectors(subsector_id),
    classification_type       TEXT NOT NULL CHECK (classification_type IN ('primary','secondary','indirect')),
    revenue_exposure          TEXT,
    classification_confidence TEXT CHECK (classification_confidence IN ('High','Medium','Low')),
    source_reference          TEXT,
    rationale                 TEXT,
    last_verified             TEXT,
    PRIMARY KEY (company_id, subsector_id)
);
CREATE INDEX IF NOT EXISTS ix_class_sub ON company_classification(subsector_id);

-- Every change to a mapping is appended here so history is never silently lost
CREATE TABLE IF NOT EXISTS classification_history (
    nse_symbol          TEXT NOT NULL,
    subsector_id        TEXT NOT NULL,
    classification_type TEXT,
    change              TEXT NOT NULL,      -- added / removed / changed
    changed_on          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_prices (       -- OHLCV cache for charts (filled on demand)
    company_id      INTEGER NOT NULL REFERENCES companies(company_id),
    date            TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL, volume REAL,
    PRIMARY KEY (company_id, date)
);

CREATE TABLE IF NOT EXISTS stock_metrics (
    company_id     INTEGER PRIMARY KEY REFERENCES companies(company_id),
    calculation_date TEXT,
    last_price_date TEXT,
    last_close     REAL,
    return_1w REAL, return_1m REAL, return_3m REAL, return_6m REAL, return_1y REAL,
    return_3y REAL, return_5y REAL,
    dma50 REAL, dma200 REAL, above_50dma INTEGER, above_200dma INTEGER,
    high_52w REAL, low_52w REAL, pct_from_52w_high REAL
);

CREATE TABLE IF NOT EXISTS financial_metrics (
    company_id       INTEGER NOT NULL REFERENCES companies(company_id),
    reporting_period TEXT NOT NULL,
    revenue REAL, revenue_growth REAL, ebitda REAL, ebitda_margin REAL,
    pat REAL, pat_growth REAL, roce REAL, roe REAL, debt REAL, debt_to_equity REAL,
    pe REAL, pb REAL, ev_ebitda REAL, dividend_yield REAL,
    source_reference TEXT, as_of TEXT,
    PRIMARY KEY (company_id, reporting_period)
);

CREATE TABLE IF NOT EXISTS group_performance (       -- sector and sub-sector, latest + history
    level            TEXT NOT NULL CHECK (level IN ('sector','subsector')),
    entity_id        TEXT NOT NULL,
    calculation_date TEXT NOT NULL,
    n_members INTEGER, n_priced INTEGER,
    ew_1w REAL, ew_1m REAL, ew_3m REAL, ew_6m REAL, ew_1y REAL, ew_3y REAL, ew_5y REAL,
    cw_1w REAL, cw_1m REAL, cw_3m REAL, cw_6m REAL, cw_1y REAL, cw_3y REAL, cw_5y REAL,
    med_1w REAL, med_1m REAL, med_3m REAL, med_6m REAL, med_1y REAL, med_3y REAL, med_5y REAL,
    xs500_1w REAL, xs500_1m REAL, xs500_3m REAL, xs500_6m REAL, xs500_1y REAL, xs500_3y REAL, xs500_5y REAL,
    xs50_3m REAL, xs50_6m REAL, xs_sector_3m REAL,
    pct_positive_3m REAL, pct_outperf_1m REAL, pct_outperf_3m REAL, pct_outperf_6m REAL,
    pct_above_50dma REAL, pct_above_200dma REAL,
    med_3m_large REAL, med_3m_mid REAL, med_3m_small REAL, med_3m_micro REAL,
    top2_share_3m REAL,
    c_relative REAL, c_absolute REAL, c_consistency REAL, c_breadth REAL, c_ma_breadth REAL,
    momentum_score REAL, rank INTEGER, eligible INTEGER,
    flags TEXT,
    PRIMARY KEY (level, entity_id, calculation_date)
);
CREATE INDEX IF NOT EXISTS ix_gp_date ON group_performance(calculation_date);

CREATE TABLE IF NOT EXISTS sector_snapshots (        -- persisted point-in-time snapshots
    calculation_date TEXT NOT NULL,
    level TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    performance_rank INTEGER, momentum_score REAL, breadth_score REAL,
    ew_1m REAL, ew_3m REAL, ew_6m REAL, pct_above_50dma REAL,
    snapshot_type TEXT,                  -- 'recorded' (as it was) or 'reconstructed'
    PRIMARY KEY (calculation_date, level, entity_id, snapshot_type)
);

CREATE TABLE IF NOT EXISTS index_series (            -- equal / cap weighted group indices
    level TEXT NOT NULL, entity_id TEXT NOT NULL, weighting TEXT NOT NULL,
    date TEXT NOT NULL, value REAL,
    PRIMARY KEY (level, entity_id, weighting, date)
);

CREATE TABLE IF NOT EXISTS refresh_log (
    component    TEXT PRIMARY KEY,
    last_refresh TEXT,
    status       TEXT,
    detail       TEXT
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


@contextmanager
def session(path: Path | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def read_sql(sql: str, params: tuple | dict = (), path: Path | None = None) -> pd.DataFrame:
    with session(path) as con:
        return pd.read_sql_query(sql, con, params=params)
