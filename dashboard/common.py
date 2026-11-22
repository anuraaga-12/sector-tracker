"""Shared Streamlit helpers: page setup, cached data access, formatting, navigation."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

from dashboard.charts import CAP_RAMP
from tracker import build, config, db, store
from tracker.analytics import PERIODS
from tracker.seed import RATING_KEYS

PERIOD_LABEL = {"1w": "1W", "1m": "1M", "3m": "3M", "6m": "6M", "1y": "1Y", "3y": "3Y CAGR", "5y": "5Y CAGR"}
CAP_ORDER = ["Large", "Mid", "Small", "Micro"]
CAP_COLORS = dict(CAP_RAMP)  # ordinal blue ramp: Large (dark) → Micro (light)
TYPE_LABEL = {"primary": "Primary", "secondary": "Secondary", "indirect": "Indirect"}
PAGES = {
    "overview": "app.py",
    "sector": "pages/1_Sector_Explorer.py",
    "subsector": "pages/2_Subsector_Deep_Dive.py",
    "company": "pages/3_Company_Explorer.py",
    "rotation": "pages/4_Sector_Rotation.py",
    "quality": "pages/5_Data_Quality.py",
}

NAV = [  # (key, label, icon) — drawn in the sidebar by setup()
    ("overview", "Market Overview", ":material/space_dashboard:"),
    ("sector", "Sector Explorer", ":material/category:"),
    ("subsector", "Sub-sector Deep Dive", ":material/troubleshoot:"),
    ("company", "Company Explorer", ":material/domain:"),
    ("rotation", "Sector Rotation", ":material/autorenew:"),
    ("funds", "Fund Holdings", ":material/account_balance:"),
    ("quality", "Data Quality", ":material/fact_check:"),
    ("methodology", "Methodology", ":material/menu_book:"),
]
PAGES["methodology"] = "pages/6_Methodology.py"
PAGES["funds"] = "pages/7_Fund_Holdings.py"

# Soft pastel light theme. Colours mirror .streamlit/config.toml and dashboard/charts.py.
CSS = """
<style>
:root {
  --ink:#2b2a3d; --ink2:#5f5d73; --muted:#8b89a0; --line:#ebe8f5; --card:#ffffff; --page:#f6f5fb;
  --violet:#6250d6; --violet-soft:#ece9ff; --blue:#2a78d6; --blue-soft:#e4effc; --aqua:#13976a; --aqua-soft:#dff5ec;
  --coral:#d94848; --coral-soft:#fde6e4; --amber:#a86f00; --amber-soft:#fff2d6; --pink-soft:#fde7f0;
  --shadow: 0 1px 2px rgba(43,42,61,.04), 0 6px 20px rgba(98,80,214,.07);
}
.block-container, [data-testid="stMainBlockContainer"] {padding-top: 3.4rem; padding-bottom: 3rem; max-width: 1400px;}
h1, h2, h3, h4 {letter-spacing: -0.015em; color: var(--ink);}
[data-testid="stHeading"] h3 {font-size: 1.2rem; margin-top: .4rem;}
[data-testid="stHeading"] h4 {font-size: 1.02rem;}
hr {border-color: var(--line) !important;}

/* ---- cards: KPI tiles, charts, tables ---- */
[data-testid="stMetric"] {background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 14px 16px 12px; box-shadow: var(--shadow); position: relative; overflow: hidden;}
[data-testid="stMetric"]::before {content: ""; position: absolute; inset: 0 0 auto 0; height: 4px; background: var(--accent, var(--violet));}
[data-testid="stColumn"]:nth-child(6n+1) [data-testid="stMetric"] {--accent: #6250d6;}
[data-testid="stColumn"]:nth-child(6n+2) [data-testid="stMetric"] {--accent: #2a78d6;}
[data-testid="stColumn"]:nth-child(6n+3) [data-testid="stMetric"] {--accent: #1baf7a;}
[data-testid="stColumn"]:nth-child(6n+4) [data-testid="stMetric"] {--accent: #eda100;}
[data-testid="stColumn"]:nth-child(6n+5) [data-testid="stMetric"] {--accent: #e87ba4;}
[data-testid="stColumn"]:nth-child(6n+6) [data-testid="stMetric"] {--accent: #eb6834;}
[data-testid="stMetricLabel"] p {color: var(--muted); font-size: .8rem; font-weight: 600;}
[data-testid="stMetricValue"] {font-size: 1.4rem; font-weight: 700; color: var(--ink); line-height: 1.25;}
[data-testid="stMetricValue"] *, [data-testid="stMetricLabel"] *, [data-testid="stMetricDelta"] * {white-space: normal !important; overflow: visible !important; text-overflow: clip !important;}
[data-testid="stPlotlyChart"] {background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 10px 8px 4px; box-shadow: var(--shadow); overflow: hidden;}
[data-testid="stDataFrame"] {border-radius: 14px; box-shadow: var(--shadow); overflow: hidden;}
[data-testid="stExpander"] details {background: var(--card); border-radius: 14px; border-color: var(--line);}

/* ---- sidebar ---- */
[data-testid="stSidebarUserContent"] {padding-top: 1rem;}
.brand {display:flex; align-items:center; gap:10px; margin: 0 0 14px 2px;}
.brand .logo {width:36px; height:36px; border-radius:11px; display:grid; place-items:center; font-size:19px;
  background: linear-gradient(135deg, #8f7ff0, #6250d6 55%, #2a78d6); color:#fff; box-shadow: 0 4px 12px rgba(98,80,214,.30);}
.brand .name {font-weight:700; color:var(--ink); line-height:1.1; font-size:.98rem;}
.brand .sub {font-size:.72rem; color:var(--muted); font-weight:500;}
[data-testid="stPageLink"] a {border-radius: 10px; padding: 6px 10px; margin: 1px 0;}
[data-testid="stPageLink"] a:hover {background: var(--violet-soft);}
[data-testid="stPageLink"] a[aria-current="page"] {background: var(--violet-soft);}
[data-testid="stPageLink"] a[aria-current="page"] p, [data-testid="stPageLink"] a[aria-current="page"] span {color: var(--violet); font-weight: 650;}
.fresh {background: #faf9fe; border: 1px solid var(--line); border-radius: 14px; padding: 12px 14px; margin-top: 6px;}
.fresh .t {font-size:.72rem; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin-bottom:8px;}
.fresh .asof {font-size:1.05rem; font-weight:700; color:var(--ink);}
.fresh .row {display:flex; justify-content:space-between; gap:8px; font-size:.76rem; color:var(--ink2); padding:3px 0;}
.fresh .row b {font-weight:600; color:var(--ink);}
.dot {display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; background: var(--aqua); vertical-align: 1px;}
.dot.warn {background: #eda100;}

/* ---- hero banner ---- */
.hero {border-radius: 22px; padding: 22px 26px; margin: 0 0 18px 0; border: 1px solid #e6e1fa;
  background: radial-gradient(1200px 300px at 0% 0%, #ebe7ff 0%, rgba(235,231,255,0) 60%),
              radial-gradient(900px 260px at 100% 0%, #ffe6ef 0%, rgba(255,230,239,0) 55%),
              radial-gradient(900px 300px at 60% 120%, #dcf5ea 0%, rgba(220,245,234,0) 60%), #ffffff;
  box-shadow: var(--shadow);}
.hero .row1 {display:flex; align-items:center; gap:14px;}
.hero .ico {width:46px; height:46px; border-radius:14px; display:grid; place-items:center; font-size:24px;
  background:#ffffffcc; border:1px solid #e6e1fa; box-shadow: 0 2px 8px rgba(98,80,214,.10);}
.hero h1 {font-size: 1.75rem; margin: 0; padding: 0; line-height: 1.2;}
.hero .lead {color: var(--ink2); font-size: .95rem; margin: 10px 0 0 0; max-width: 980px;}
.hero .chips {margin-top: 12px; display:flex; flex-wrap:wrap; gap:6px;}
.chip {display:inline-flex; align-items:center; gap:6px; font-size:.76rem; font-weight:600; padding:4px 10px;
  border-radius:999px; background:#ffffffd9; border:1px solid var(--line); color: var(--ink2);}
.chip.v {background: var(--violet-soft); color: #4a3cc0; border-color: #ddd7fb;}
.chip.g {background: var(--aqua-soft); color: #0d7a55; border-color: #c8ecdd;}
.chip.a {background: var(--amber-soft); color: var(--amber); border-color: #f6e2b5;}
.disc {font-size:.74rem; color: var(--muted); margin-top: 10px;}

/* ---- list cards (overview) ---- */
.lcard {background: var(--card); border: 1px solid var(--line); border-radius: 16px; padding: 14px 14px 8px;
  box-shadow: var(--shadow); height: 100%;}
.lcard .hd {display:flex; align-items:center; gap:8px; font-weight:700; color:var(--ink); font-size:.92rem; margin-bottom:8px;}
.lcard .hd .pill {width:26px; height:26px; border-radius:9px; display:grid; place-items:center; font-size:14px;}
.lrow {display:flex; align-items:center; gap:10px; padding: 7px 4px; border-top: 1px solid #f2f0f8;}
.lrow:first-of-type {border-top: none;}
.lrow .rk {min-width:24px; height:24px; border-radius:8px; display:grid; place-items:center; font-size:.75rem; font-weight:700;
  background: var(--violet-soft); color: var(--violet);}
.lrow .nm {flex:1; min-width:0;}
.lrow .nm .a {font-size:.86rem; font-weight:600; color:var(--ink); line-height:1.25; overflow-wrap:break-word;}
.lrow .nm .b {font-size:.72rem; color:var(--muted); line-height:1.3; margin-top:1px;}
.val {font-size:.8rem; font-weight:700; padding:3px 8px; border-radius:8px; white-space:nowrap;}
.val.up {background: var(--aqua-soft); color: #0d7a55;}
.val.dn {background: var(--coral-soft); color: #b83434;}
.val.nt {background: #f1f0f6; color: var(--ink2);}
.empty {font-size:.8rem; color: var(--muted); padding: 6px 4px 10px;}

/* ---- tags, value chain ---- */
.tag {display:inline-block;padding:3px 10px;margin:2px 4px 2px 0;border-radius:999px;font-size:0.76rem;font-weight:600;
      background:#f1f0f6;color:var(--ink2);border:1px solid var(--line)}
.tag.primary {background:var(--violet-soft);color:#4a3cc0;border-color:#ddd7fb}
.tag.secondary {background:var(--blue-soft);color:#1c5cab;border-color:#cfe1f8}
.tag.indirect {background:#f1f0f6;color:var(--ink2)}
.tag.flag {background:var(--amber-soft);color:var(--amber);border-color:#f6e2b5}
.chain {display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px 0; align-items:center}
.chain span {background:#ffffff;border:1px solid var(--line);border-radius:10px;padding:6px 11px;font-size:0.84rem;color:var(--ink2)}
.chain span.on {background:linear-gradient(135deg,#7b6cf0,#6250d6);color:white;border-color:#6250d6;box-shadow:0 3px 10px rgba(98,80,214,.25)}
.small {font-size:0.82rem;color:var(--muted)}
.demo {background:#fde6e4;color:#a12f2f;border:1px solid #f6c9c4;padding:10px 14px;border-radius:12px;font-weight:600;margin-bottom:12px}
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
    sidebar_nav()
    sidebar_status()


def sidebar_nav() -> None:
    with st.sidebar:
        st.markdown("<div class='brand'><div class='logo'>📈</div><div><div class='name'>India Sector Tracker</div>"
                    "<div class='sub'>Sectors · themes · momentum</div></div></div>", unsafe_allow_html=True)
        for key, label, icon in NAV:
            st.page_link(PAGES[key], label=label, icon=icon)


def _fmt_date(d) -> str:
    try:
        return pd.Timestamp(d).strftime("%d %b %Y")
    except Exception:
        return str(d or "n/a")


def sidebar_status() -> None:
    log = freshness()
    labels = [("prices", "Prices"), ("market_cap", "Market caps"), ("fundamentals", "Fundamentals"),
              ("funds", "Fund data"), ("database_build", "Last build")]
    rows = []
    for key, lab in labels:
        row = log.get(key)
        if row is None:
            rows.append(f"<div class='row'><span><span class='dot warn'></span>{lab}</span><b>never</b></div>")
        else:
            ts = pd.Timestamp(row["last_refresh"])
            ts = ts.tz_convert("Asia/Kolkata") if ts.tzinfo else ts
            dot = "dot" if row["status"] == "ok" else "dot warn"
            rows.append(f"<div class='row'><span><span class='{dot}'></span>{lab}</span><b>{ts:%d %b, %H:%M}</b></div>")
    with st.sidebar:
        st.markdown(f"<div class='fresh'><div class='t'>Data as of</div><div class='asof'>{_fmt_date(as_of())}</div>"
                    f"<div class='small' style='margin:2px 0 8px'>End-of-day closes · refreshed 19:00 IST</div>"
                    + "".join(rows) + "</div>", unsafe_allow_html=True)
        st.caption("Research tool — not investment advice. Momentum scores describe past price behaviour only.")


def hero(title: str, lead: str = "", icon: str = "📊", chips: list[tuple[str, str]] | None = None,
         disclaimer: bool = False) -> None:
    """Gradient header banner. chips: [(text, kind)] with kind in '', 'v', 'g', 'a'."""
    chip_html = "".join(f"<span class='chip {k}'>{t}</span>" for t, k in (chips or []))
    st.markdown(
        f"<div class='hero'><div class='row1'><div class='ico'>{icon}</div><h1>{title}</h1></div>"
        + (f"<p class='lead'>{lead}</p>" if lead else "")
        + (f"<div class='chips'>{chip_html}</div>" if chip_html else "")
        + (f"<div class='disc'>{DISCLAIMER}</div>" if disclaimer else "")
        + "</div>", unsafe_allow_html=True)


def tone(x) -> str:
    """CSS class for a signed value: up / dn / nt."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "nt"
    return "up" if x > 0 else "dn" if x < 0 else "nt"


def list_card(title: str, rows: list[dict], icon: str = "★", accent: str = "v", empty: str = "Nothing to show.") -> str:
    """HTML card with ranked rows. row: rank, name, sub, value, tone ('up'/'dn'/'nt')."""
    pill_bg = {"v": "var(--violet-soft)", "g": "var(--aqua-soft)", "r": "var(--coral-soft)", "a": "var(--amber-soft)"}[accent]
    body = "".join(
        f"<div class='lrow'><div class='rk'>{r.get('rank', '')}</div><div class='nm'><div class='a'>{r['name']}</div>"
        f"<div class='b'>{r.get('sub', '')}</div></div>"
        + (f"<span class='val {r.get('tone', 'nt')}'>{r['value']}</span>" if r.get("value") else "") + "</div>"
        for r in rows) or f"<div class='empty'>{empty}</div>"
    return (f"<div class='lcard'><div class='hd'><span class='pill' style='background:{pill_bg}'>{icon}</span>{title}</div>"
            f"{body}</div>")


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


@st.cache_data(ttl=3600, show_spinner=False)
def _mf(version: tuple) -> dict:
    from tracker import funds as F
    hold = store.read_table(config.MF_HOLDINGS_FILE)
    if not hold.empty:
        hold["amfi"] = hold["amfi"].astype(str)
    meta = (pd.read_csv(config.MF_FUNDS_FILE, dtype=str, keep_default_na=False)
            if config.MF_FUNDS_FILE.exists() else F.fund_list())
    return {"funds": meta, "nav": store.read_wide(config.MF_NAV_FILE), "holdings": hold,
            "ref": store.read_table(config.ISIN_FILE)}


def mf_data() -> dict:
    """Mutual-fund files (cached; reloaded whenever the refresh rewrites them)."""
    files = (config.MF_FUNDS_FILE, config.MF_NAV_FILE, config.MF_HOLDINGS_FILE, config.ISIN_FILE)
    return _mf(tuple(p.stat().st_mtime if p.exists() else 0.0 for p in files))


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
