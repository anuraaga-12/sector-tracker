"""Shared Streamlit helpers: page setup, cached data access, formatting, navigation."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

from tracker import build, config, db, store
from tracker.analytics import PERIODS
from tracker.seed import RATING_KEYS

PERIOD_LABEL = {"1w": "1W", "1m": "1M", "3m": "3M", "6m": "6M", "1y": "1Y", "3y": "3Y CAGR", "5y": "5Y CAGR"}
CAP_ORDER = ["Large", "Mid", "Small", "Micro"]
CAP_COLORS = {"Large": "#1f4e79", "Mid": "#2e86c1", "Small": "#f39c12", "Micro": "#e74c3c", "Unknown": "#95a5a6"}
TYPE_LABEL = {"primary": "Primary", "secondary": "Secondary", "indirect": "Indirect"}
PAGES = {
    "overview": "app.py",
    "sector": "pages/1_Sector_Explorer.py",
    "subsector": "pages/2_Subsector_Deep_Dive.py",
    "company": "pages/3_Company_Explorer.py",
    "rotation": "pages/4_Sector_Rotation.py",
    "quality": "pages/5_Data_Quality.py",
}

CSS = """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
div[data-testid="stMetricValue"] {font-size: 1.45rem;}
.tag {display:inline-block;padding:2px 9px;margin:2px 4px 2px 0;border-radius:12px;font-size:0.78rem;
      background:#eef2f7;color:#1f2d3d;border:1px solid #d6dee8}
.tag.primary {background:#1f4e79;color:#fff;border-color:#1f4e79}
.tag.secondary {background:#d6e9f8;color:#1f4e79;border-color:#9cc3e6}
.tag.flag {background:#fff4e0;color:#8a5300;border-color:#f3c77a}
.chain {display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px 0}
.chain span {background:#f3f6fa;border:1px solid #d6dee8;border-radius:6px;padding:6px 10px;font-size:0.85rem}
.chain span.on {background:#1f4e79;color:white;border-color:#1f4e79}
.small {font-size:0.82rem;color:#5d6d7e}
.demo {background:#c0392b;color:white;padding:8px 14px;border-radius:6px;font-weight:600;margin-bottom:10px}
</style>
"""


# ----------------------------------------------------------------------------- setup
@st.cache_resource(show_spinner="Building the database from seed and market files …")
def _ensure_db(_stamp: float) -> float:
    build.ensure_database(log=print)
    return config.DB_PATH.stat().st_mtime


def db_version() -> float:
    stamp = max((p.stat().st_mtime for p in build._inputs()), default=0.0)
    return _ensure_db(stamp)


def setup(title: str, icon: str = "📊") -> None:
    st.set_page_config(page_title=f"{title} · India Sector Tracker", page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    if config.DATA_MODE == "demo":
        st.markdown('<div class="demo">⚠️ DEMO MODE — all prices, market caps and fundamentals are SYNTHETIC. '
                    'Do not use for analysis.</div>', unsafe_allow_html=True)
    db_version()
    sidebar_status()


def sidebar_status() -> None:
    log = freshness()
    with st.sidebar:
        st.markdown("### Data freshness")
        labels = [("prices", "Stock prices"), ("market_cap", "Market cap (shares)"),
                  ("fundamentals", "Fundamentals"), ("classification_seed", "Classification seed"),
                  ("database_build", "Database build")]
        for key, lab in labels:
            row = log.get(key)
            if row is None:
                st.markdown(f"<span class='small'>{lab}: <b>never</b></span>", unsafe_allow_html=True)
            else:
                ts = str(row["last_refresh"])[:16].replace("T", " ")
                bad = "" if row["status"] == "ok" else " ⚠️"
                st.markdown(f"<span class='small'>{lab}: <b>{ts}</b>{bad}</span>", unsafe_allow_html=True)
        asof = as_of()
        st.markdown(f"<span class='small'>Latest market date in data: <b>{asof or 'n/a'}</b><br>"
                    "Data is end-of-day, not live.</span>", unsafe_allow_html=True)
        st.caption("Research tool — not investment advice. Momentum scores describe past price behaviour only.")


# ----------------------------------------------------------------------------- data access
@st.cache_data(ttl=3600, show_spinner=False)
def _q(sql: str, params: tuple, _v: float) -> pd.DataFrame:
    return db.read_sql(sql, params)


def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _q(sql, params, db_version())


def freshness() -> dict:
    df = q("SELECT component, last_refresh, status, detail FROM refresh_log")
    return {r.component: r._asdict() for r in df.itertuples(index=False)}


def as_of() -> str | None:
    d = q("SELECT MAX(calculation_date) AS d FROM group_performance")
    return d["d"].iloc[0] if not d.empty else None


def sectors() -> pd.DataFrame:
    return q("SELECT * FROM sectors ORDER BY priority, sector_name")


def subsectors() -> pd.DataFrame:
    df = q("""SELECT s.*, x.sector_name FROM subsectors s JOIN sectors x USING(sector_id)
              ORDER BY x.priority, x.sector_name, s.subsector_name""")
    df["profile"] = df["profile_json"].map(lambda s: json.loads(s) if s else {})
    return df


def companies() -> pd.DataFrame:
    return q("""SELECT c.*, m.last_close, m.last_price_date, m.return_1w, m.return_1m, m.return_3m, m.return_6m,
                       m.return_1y, m.return_3y, m.return_5y, m.dma50, m.dma200, m.above_50dma, m.above_200dma,
                       m.high_52w, m.low_52w, m.pct_from_52w_high
                FROM companies c LEFT JOIN stock_metrics m USING(company_id)""")


def classifications() -> pd.DataFrame:
    return q("""SELECT cc.*, c.nse_symbol, c.company_name, s.subsector_name, s.sector_id, x.sector_name
                FROM company_classification cc JOIN companies c USING(company_id)
                JOIN subsectors s USING(subsector_id) JOIN sectors x ON x.sector_id = s.sector_id""")


def fundamentals() -> pd.DataFrame:
    return q("""SELECT f.*, c.nse_symbol FROM financial_metrics f JOIN companies c USING(company_id)""")


def perf(level: str, date: str | None = None) -> pd.DataFrame:
    date = date or as_of()
    df = q("SELECT * FROM group_performance WHERE level = ? AND calculation_date = ?", (level, date))
    if level == "sector":
        names = sectors()[["sector_id", "sector_name"]].rename(columns={"sector_id": "entity_id", "sector_name": "name"})
        df = df.merge(names, on="entity_id", how="left")
        df["sector_name"] = df["name"]
    else:
        names = subsectors()[["subsector_id", "subsector_name", "sector_id", "sector_name"]].rename(
            columns={"subsector_id": "entity_id", "subsector_name": "name"})
        df = df.merge(names, on="entity_id", how="left")
    return df


def perf_history(level: str) -> pd.DataFrame:
    return q("SELECT * FROM group_performance WHERE level = ? ORDER BY calculation_date", (level,))


def snapshots(level: str) -> pd.DataFrame:
    return q("SELECT * FROM sector_snapshots WHERE level = ? ORDER BY calculation_date", (level,))


def index_series(level: str, entity: str) -> pd.DataFrame:
    df = q("SELECT weighting, date, value FROM index_series WHERE level=? AND entity_id=?", (level, entity))
    if df.empty:
        return df
    out = df.pivot(index="date", columns="weighting", values="value")
    out.index = pd.to_datetime(out.index)
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def _wide(path: str, _v: float) -> pd.DataFrame:
    return store.read_wide(path)


def prices() -> pd.DataFrame:
    return _wide(str(config.PRICES_FILE), db_version())


def benchmarks() -> pd.DataFrame:
    return _wide(str(config.BENCH_FILE), db_version())


# ----------------------------------------------------------------------------- formatting
def pct(x, digits=1) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x * 100:+.{digits}f}%"


def num(x, digits=0) -> str:
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{digits}f}"


def crore(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"₹{x / 1e5:,.2f} lakh cr" if x >= 1e5 else f"₹{x:,.0f} cr"


def as_pct_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        if c in df:
            df[c] = df[c] * 100
    return df


def pct_col(label: str, help: str | None = None):
    return st.column_config.NumberColumn(label, format="%.1f%%", help=help)


def score_col(label: str = "Momentum score", help: str | None = None):
    return st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.0f", help=help)


def tags(items: list[str], kind: str = "") -> str:
    return " ".join(f"<span class='tag {kind}'>{i}</span>" for i in items if i)


def chain_html(steps: list[str], highlight: str | None = None) -> str:
    out = []
    for s in steps:
        on = " on" if highlight and highlight.lower() in s.lower() else ""
        out.append(f"<span class='{on.strip()}'>{s}</span>")
    return "<div class='chain'>" + " ➜ ".join(out) + "</div>"


def goto(page: str, **state) -> None:
    for k, v in state.items():
        st.session_state[k] = v
    st.switch_page(PAGES[page])


def pick_index(options: list, value, default: int = 0) -> int:
    try:
        return options.index(value)
    except ValueError:
        return default


def ratings_table(profile: dict) -> pd.DataFrame:
    r = profile.get("ratings", {})
    good_when_high = {"growth", "barriers", "pricing", "margins", "roce", "structural"}
    rows = []
    for k, lab in RATING_KEYS.items():
        v = r.get(k)
        if v is None:
            continue
        if k in good_when_high:
            tone = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}[v]
        elif k in ("export", "regulation"):
            tone = "⚪"
        else:
            tone = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}[v]
        rows.append({"Dimension": lab, "Assessment": v, "": tone})
    return pd.DataFrame(rows)


DISCLAIMER = ("This is a market-intelligence and research tool, not a recommendation to buy or sell any security. "
              "Classifications are an initial analyst mapping with stated confidence levels; verify against company "
              "filings before relying on them.")
