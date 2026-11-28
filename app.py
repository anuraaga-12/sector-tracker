"""Market Overview — entry point:  streamlit run app.py"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import config
from tracker.analytics import series_return

C.setup("Market Overview", "🧭")

sec = C.perf("sector")
sub = C.perf("subsector")
cls = C.classifications()
comp = C.companies()

_n_lead = int((sec["xs500_1m"] > 0).sum()) if "xs500_1m" in sec else 0
C.hero("Indian Equity Sector Tracker",
       "Which sectors and granular themes are leading the Indian market — and is the move broad-based?",
       icon="🧭", disclaimer=True,
       chips=[(f"📅 Data as of {C._fmt_date(C.as_of())}", "v"),
              (f"🏭 {C.sectors().shape[0]} sectors · {C.subsectors().shape[0]} themes", ""),
              (f"🏢 {comp['nse_symbol'].nunique()} NSE companies", ""),
              (f"▲ {_n_lead} sectors beating Nifty 500 (1M)", "g")])

if sec.empty or sec["ew_1m"].isna().all():
    st.warning("No price data yet. Run `python -m tracker.refresh daily` (or the scheduled GitHub Action) to "
               "download prices — the taxonomy and company universe below are already browsable.")

# --------------------------------------------------------------------------- KPIs
k = st.columns(6)
k[0].metric("Sectors", C.sectors().shape[0])
k[1].metric("Sub-sectors", C.subsectors().shape[0])
k[2].metric("Companies", comp["nse_symbol"].nunique())
k[3].metric("With prices", int(comp["last_price_date"].notna().sum()))
bench = C.benchmarks()
cfgb = config.settings()["benchmarks"]
for i, (lab, t) in enumerate((("Nifty 50 · 3M", cfgb["nifty50"]), ("Nifty 500 · 3M", cfgb["nifty500"]))):
    if t in bench and bench[t].notna().sum() > 70:
        s = bench[t].dropna()
        k[4 + i].metric(lab, C.pct(series_return(s, len(s) - 1, "3m")),
                        help=f"1M {C.pct(series_return(s, len(s) - 1, '1m'))} · 1Y {C.pct(series_return(s, len(s) - 1, '1y'))}")
    else:
        k[4 + i].metric(lab, "—")

ranked_sec = sec[sec["eligible"] == 1].sort_values("momentum_score", ascending=False)
ranked_sub = sub[sub["eligible"] == 1].sort_values("momentum_score", ascending=False)


def _flagged(df, flag):
    return df[df["flags"].fillna("").str.contains(flag)]


# --------------------------------------------------------------------------- headline lists
w = _flagged(ranked_sub, "Weakening momentum").sort_values("momentum_score").head(5)
e = pd.concat([_flagged(ranked_sub, "Early strength"), _flagged(ranked_sub, "Small caps leading")]).drop_duplicates("entity_id")
cards = [
    C.list_card("Leading sectors · 3M", [
        {"rank": int(r.rank), "name": r.name, "sub": f"Momentum score {r.momentum_score:.0f}",
         "value": C.pct(r.ew_3m), "tone": C.tone(r.ew_3m)} for r in ranked_sec.head(5).itertuples()],
        icon="🏆", accent="v"),
    C.list_card("Leading sub-sectors · 3M", [
        {"rank": int(r.rank), "name": r.name, "sub": r.sector_name,
         "value": C.pct(r.ew_3m), "tone": C.tone(r.ew_3m)} for r in ranked_sub.head(5).itertuples()],
        icon="🚀", accent="g"),
    C.list_card("Weakening · 1M", [
        {"rank": "▼", "name": r.name, "sub": f"{r.sector_name} · score {r.momentum_score:.0f}",
         "value": C.pct(r.ew_1m), "tone": C.tone(r.ew_1m)} for r in w.itertuples()],
        icon="📉", accent="r", empty="No sub-sector lost ≥ the configured score drop over 1M."),
    C.list_card("Emerging momentum · 1M", [
        {"rank": "▲", "name": r.name, "sub": r.flags.replace("|", " · "),
         "value": C.pct(r.ew_1m), "tone": C.tone(r.ew_1m)} for r in e.head(5).itertuples()],
        icon="🌱", accent="a", empty="No early-strength or small-cap-led themes flagged right now."),
]
for pair in (cards[:2], cards[2:]):
    for col, html in zip(st.columns(2, gap="medium"), pair):
        col.markdown(html, unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

st.divider()

# --------------------------------------------------------------------------- heatmap
st.subheader("Sector heatmap")
h1, h2 = st.columns([2, 3])
basis = h1.radio("Return basis", ["Equal-weighted", "Median stock", "Cap-weighted"], horizontal=True)
rel = h2.radio("Show", ["Absolute return", "Excess vs Nifty 500"], horizontal=True)
pre = {"Equal-weighted": "ew", "Median stock": "med", "Cap-weighted": "cw"}[basis]
periods = ["1w", "1m", "3m", "6m", "1y", "3y", "5y"]
hm = sec.set_index("name")[[f"{pre}_{p}" for p in periods]].copy()
if rel == "Excess vs Nifty 500":
    if pre == "ew":
        hm = sec.set_index("name")[[f"xs500_{p}" for p in periods]].copy()
    else:
        b = bench[cfgb["nifty500"]].dropna() if cfgb["nifty500"] in bench else pd.Series(dtype=float)
        for p in periods:
            br = series_return(b, len(b) - 1, p) if len(b) else float("nan")
            hm[f"{pre}_{p}"] = hm[f"{pre}_{p}"] - br
hm.columns = [C.PERIOD_LABEL[p] for p in periods]
order = sec.set_index("name")["momentum_score"].sort_values(ascending=False).index
hm = (hm.reindex(order) * 100)
st.plotly_chart(charts.heatmap(hm, title=f"{basis} · {rel.lower()} (sorted by momentum score)"), theme=None)

# --------------------------------------------------------------------------- tables
pc = ["ew_1w", "ew_1m", "ew_3m", "ew_6m", "ew_1y", "xs500_1m", "xs500_3m", "xs500_6m", "med_3m",
      "pct_outperf_3m", "pct_above_50dma", "pct_above_200dma"]


def table(df: pd.DataFrame, cols: list[str], n: int = 10, key: str = "", show_sector: bool = True):
    d = df.head(n)[["name"] + (["sector_name"] if show_sector else []) + cols].copy()
    d = C.as_pct_cols(d, [c for c in cols if c.startswith(("ew_", "xs", "med_", "cw_"))])
    cfg = {"name": "Name", "sector_name": "Sector", "momentum_score": C.score_col(),
           "n_priced": st.column_config.NumberColumn("Stocks"), "flags": "Signals"}
    for c in cols:
        if c.startswith(("ew_", "xs500", "med_", "cw_")):
            p = c.split("_")[-1]
            lab = {"ew": "", "xs500": "vs N500 ", "med": "Median ", "cw": "Cap-wt "}[c.split("_")[0]]
            cfg[c] = C.pct_col(f"{lab}{C.PERIOD_LABEL.get(p, p)}")
        if c.startswith("pct_"):
            cfg[c] = st.column_config.NumberColumn({"pct_outperf_3m": "% beating N500 (3M)", "pct_above_50dma": "% > 50DMA",
                                                    "pct_above_200dma": "% > 200DMA", "pct_positive_3m": "% positive (3M)"}.get(c, c),
                                                   format="%.0f%%")
    st.dataframe(d, column_config=cfg, hide_index=True, key=key or None)


t1, t2 = st.columns(2)
with t1:
    st.markdown("#### Top 10 sectors · 1M")
    table(sec[sec["eligible"] == 1].sort_values("ew_1m", ascending=False),
          ["ew_1m", "xs500_1m", "ew_3m", "pct_outperf_3m", "momentum_score"], key="ts1m", show_sector=False)
with t2:
    st.markdown("#### Top 10 sub-sectors · 3M")
    table(ranked_sub.sort_values("ew_3m", ascending=False),
          ["ew_3m", "xs500_3m", "med_3m", "pct_outperf_3m", "n_priced"], key="tss3m")
t3, t4 = st.columns(2)
with t3:
    st.markdown("#### Top 10 sub-sectors · 6M")
    table(ranked_sub.sort_values("ew_6m", ascending=False),
          ["ew_6m", "xs500_6m", "med_3m", "pct_above_200dma", "n_priced"], key="tss6m")
with t4:
    st.markdown("#### Improving breadth")
    st.caption("Share of constituents above their 50-DMA rose by ≥ the configured threshold over 1M.")
    table(_flagged(ranked_sub, "Improving breadth").sort_values("pct_above_50dma", ascending=False),
          ["pct_above_50dma", "pct_above_200dma", "ew_1m", "flags"], key="ib")
t5, t6 = st.columns(2)
with t5:
    st.markdown("#### Weakening momentum")
    table(_flagged(ranked_sub, "Weakening momentum").sort_values("momentum_score"),
          ["momentum_score", "ew_1m", "xs500_1m", "pct_above_50dma"], key="wm")
with t6:
    st.markdown("#### Narrow leadership (few heavyweights driving the move)")
    table(_flagged(ranked_sub, "Narrow leadership").sort_values("ew_3m", ascending=False),
          ["cw_3m", "med_3m", "top2_share_3m", "pct_outperf_3m"], key="nl")

st.divider()
st.markdown("#### Drill down")
d1, d2, d3 = st.columns([2, 2, 1])
sec_names = C.sectors()["sector_name"].tolist()
pick = d1.selectbox("Open a sector", sec_names, index=None, placeholder="Choose sector…")
if pick:
    sid = C.sectors().set_index("sector_name").loc[pick, "sector_id"]
    C.goto("sector", sector_id=sid)
subs = C.subsectors()
labels = (subs["sector_name"] + " › " + subs["subsector_name"]).tolist()
pick2 = d2.selectbox("Open a sub-sector", labels, index=None, placeholder="Choose sub-sector…")
if pick2:
    C.goto("subsector", subsector_id=subs.iloc[labels.index(pick2)]["subsector_id"])
