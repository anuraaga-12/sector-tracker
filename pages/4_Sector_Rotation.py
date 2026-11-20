"""Sector Rotation — how leadership changes over time."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import analytics, config

C.setup("Sector Rotation", "🔄")
st.title("🔄 Sector Rotation")
st.caption("Momentum scores rank past price behaviour relative to peers. They are descriptive, not predictive, and are "
           "not investment recommendations.")

cfg = config.settings()
top = st.columns([2, 2, 3])
level = top[0].radio("Level", ["sector", "subsector"], format_func=lambda x: "Sectors" if x == "sector" else "Sub-sectors",
                     horizontal=True)
secs = C.sectors()
sec_filter = None
if level == "subsector":
    sec_filter = top[1].multiselect("Limit to sectors", secs["sector_id"].tolist(),
                                    format_func=dict(zip(secs["sector_id"], secs["sector_name"])).get)
seg = top[2].radio("Market-cap lens (3M median return)", ["All", "Large", "Mid", "Small", "Micro"], horizontal=True)

# --------------------------------------------------------------------------- configurable score
with st.expander("⚖️ Momentum score weights (recomputed live)", expanded=False):
    w0 = cfg["momentum"]["weights"]
    wc = st.columns(5)
    weights = {k: wc[i].slider(lab, 0.0, 1.0, float(w0[k]), 0.05) for i, (k, lab) in enumerate([
        ("relative", "Relative perf"), ("absolute", "Absolute perf"), ("consistency", "Consistency"),
        ("breadth", "Breadth"), ("ma_breadth", "% above MAs")])}
    st.caption("Each component is a 0-100 percentile across eligible peers. Score = weighted average of components. "
               "Edit defaults in settings.yaml.")

now = C.perf(level)
if sec_filter:
    now = now[now["sector_id"].isin(sec_filter)]
now = now[now["eligible"] == 1].copy()
if now.empty:
    st.info("No ranked groups yet — price data needed.")
    st.stop()
now["score"] = analytics.score(now, weights)
now["rank_now"] = now["score"].rank(ascending=False, method="min")

hist = C.perf_history(level)
names = now.set_index("entity_id")["name"].to_dict()
hist = hist[hist["entity_id"].isin(names)]
dates = sorted(hist["calculation_date"].unique())
latest = dates[-1]
d_idx = pd.to_datetime(pd.Series(dates))


def _nearest(months_back: int) -> str:
    target = pd.to_datetime(latest) - pd.DateOffset(months=months_back)
    return dates[int((d_idx - target).abs().idxmin())]


def _ranked_at(d: str) -> pd.DataFrame:
    h = hist[hist["calculation_date"] == d].copy()
    h["score"] = analytics.score(h, weights)
    h["rank"] = h["score"].rank(ascending=False, method="min")
    return h.set_index("entity_id")


m1, m3 = _ranked_at(_nearest(1)), _ranked_at(_nearest(3))
now["rank_1m_ago"] = now["entity_id"].map(m1["rank"])
now["rank_3m_ago"] = now["entity_id"].map(m3["rank"])
now["score_1m_ago"] = now["entity_id"].map(m1["score"])
now["d_score_1m"] = now["score"] - now["score_1m_ago"]
if seg != "All":
    now["lens"] = now[f"med_3m_{seg.lower()}"] * 100

# --------------------------------------------------------------------------- narrative boxes
b = st.columns(4)
lead_now = now.sort_values("score", ascending=False).head(5)
lead_3m = now.sort_values("rank_3m_ago").head(5)
losing = now[now["d_score_1m"] <= -cfg["rotation"]["improving_score_delta"]].sort_values("d_score_1m").head(5)
early = now[(now["rank_3m_ago"] > len(now) / 2) & (now["d_score_1m"] > 0) & (now["xs500_1m"] > 0)].sort_values(
    "d_score_1m", ascending=False).head(5)
for col, title, df, fmt in ((b[0], "Leading 3 months ago", lead_3m, lambda r: f"#{int(r.rank_3m_ago)} then → #{int(r.rank_now)} now"),
                            (b[1], "Leading now", lead_now, lambda r: f"score {r.score:.0f}"),
                            (b[2], "Losing momentum", losing, lambda r: f"Δ score {r.d_score_1m:+.0f}"),
                            (b[3], "Early signs of strength", early, lambda r: f"was #{int(r.rank_3m_ago)}")):
    with col:
        st.markdown(f"**{title}**")
        if df.empty:
            st.caption("None flagged.")
        for r in df.itertuples():
            try:
                extra = fmt(r)
            except (ValueError, TypeError):  # NaN rank (e.g. group not eligible 3M ago)
                extra = ""
            st.markdown(f"- {r.name} <span class='small'>· {extra}</span>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- leaderboard
st.subheader("Leaderboard")
lb = now.sort_values("score", ascending=False)
cols = ["name"] + (["sector_name"] if level == "subsector" else []) + [
    "score", "rank_now", "rank_1m_ago", "rank_3m_ago", "d_score_1m", "ew_1m", "ew_3m", "ew_6m", "xs500_3m",
    "pct_outperf_3m", "pct_above_50dma", "c_relative", "c_absolute", "c_consistency", "c_breadth", "c_ma_breadth", "flags"]
if seg != "All":
    cols.insert(cols.index("ew_1m"), "lens")
d = C.as_pct_cols(lb[cols], ["ew_1m", "ew_3m", "ew_6m", "xs500_3m"])
st.dataframe(d, hide_index=True, height=min(700, 36 * len(d) + 40), column_config={
    "name": "Name", "sector_name": "Sector", "score": C.score_col("Score"), "rank_now": "Rank",
    "rank_1m_ago": "Rank 1M ago", "rank_3m_ago": "Rank 3M ago", "d_score_1m": st.column_config.NumberColumn("Δ score 1M", format="%+.0f"),
    "ew_1m": C.pct_col("1M"), "ew_3m": C.pct_col("3M"), "ew_6m": C.pct_col("6M"), "xs500_3m": C.pct_col("vs N500 3M"),
    "lens": C.pct_col(f"{seg}-cap median 3M"),
    "pct_outperf_3m": st.column_config.NumberColumn("% beating N500", format="%.0f%%"),
    "pct_above_50dma": st.column_config.NumberColumn("% > 50DMA", format="%.0f%%"),
    "c_relative": st.column_config.NumberColumn("Rel", format="%.0f"), "c_absolute": st.column_config.NumberColumn("Abs", format="%.0f"),
    "c_consistency": st.column_config.NumberColumn("Consist.", format="%.0f"), "c_breadth": st.column_config.NumberColumn("Breadth", format="%.0f"),
    "c_ma_breadth": st.column_config.NumberColumn("MA", format="%.0f"), "flags": "Signals"})

# --------------------------------------------------------------------------- RRG
st.subheader("Relative rotation map")
bench = C.benchmarks()
n500 = cfg["benchmarks"]["nifty500"]
if n500 not in bench:
    st.info("Nifty 500 benchmark data needed for the rotation map.")
else:
    pts, tails = [], []
    nb = bench[n500].dropna()
    ids = lb["entity_id"].tolist()[: 40 if level == "subsector" else 30]
    for eid in ids:
        idx = C.index_series(level, eid)
        if idx.empty or "ew" not in idx:
            continue
        s = idx["ew"].reindex(nb.index).ffill()
        rs = s / nb
        ratio = 100 * rs / rs.rolling(63, min_periods=40).mean()
        mom = 100 * ratio / ratio.shift(10)
        dfp = pd.DataFrame({"x": ratio, "y": mom}).dropna()
        if dfp.empty:
            continue
        nm = names.get(eid, eid)
        pts.append({"name": nm, "x": dfp["x"].iloc[-1], "y": dfp["y"].iloc[-1]})
        tl = dfp.iloc[::-5].head(6).iloc[::-1]
        tails.append(tl.assign(name=nm))
    if pts:
        st.plotly_chart(charts.rrg(pd.DataFrame(pts), pd.concat(tails) if tails else None,
                                   "Equal-weighted index vs Nifty 500 (simplified RRG; tails = last ~6 weeks)"))
        st.caption("x > 100: outperforming Nifty 500 over the trailing ~3 months; y > 100: that relative strength is rising. "
                   "Groups typically rotate clockwise Improving → Leading → Weakening → Lagging, but not always.")

# --------------------------------------------------------------------------- rank history
st.subheader("Leadership over time")
snap_type = st.radio("Snapshot source", ["reconstructed", "recorded"], horizontal=True,
                     format_func=lambda x: {"reconstructed": "Reconstructed month-ends (current classification)",
                                            "recorded": "Recorded by the daily job (as shown at the time)"}[x])
sn = C.snapshots(level)
sn = sn[(sn["snapshot_type"] == snap_type) & sn["entity_id"].isin(names)]
if sn.empty:
    st.info("No snapshots of this type yet. Recorded snapshots accumulate once the scheduled refresh runs daily.")
else:
    default = lb["entity_id"].head(6).tolist()
    pick = st.multiselect("Groups to plot", list(names), default=default, format_func=names.get)
    pv = sn[sn["entity_id"].isin(pick)].pivot_table(index="calculation_date", columns="entity_id", values="performance_rank")
    pv.index = pd.to_datetime(pv.index)
    pv = pv.rename(columns=names)
    st.plotly_chart(charts.rank_lines(pv, "Momentum rank (default weights) — lower is stronger"))
    hm = sn.pivot_table(index="entity_id", columns="calculation_date", values="momentum_score")
    hm = hm.reindex([e for e in lb["entity_id"] if e in hm.index]).rename(index=names)
    hm.columns = [pd.to_datetime(c).strftime("%b-%y") for c in hm.columns]
    hm = hm.T.groupby(level=0, sort=False).last().T  # one column per month label
    st.plotly_chart(charts.heatmap(hm.iloc[:40, -18:], "Momentum score by month (0-100)", zmid=50, fmt="{:.0f}"))

# --------------------------------------------------------------------------- breadth & participation
st.subheader("Breadth & participation")
focus = st.selectbox("Group", list(names), format_func=names.get, index=0)
hh = hist[hist["entity_id"] == focus].copy()
hh["date"] = pd.to_datetime(hh["calculation_date"])
hh = hh.set_index("date").sort_index()
c1, c2 = st.columns(2)
c1.plotly_chart(charts.lines(hh[["pct_above_50dma", "pct_above_200dma", "pct_outperf_3m"]].rename(columns={
    "pct_above_50dma": "% above 50-DMA", "pct_above_200dma": "% above 200-DMA", "pct_outperf_3m": "% beating N500 (3M)"}),
    f"Breadth trend — {names[focus]}", "%"))
cap = hh[[f"med_3m_{c.lower()}" for c in C.CAP_ORDER]] * 100
cap.columns = [f"{c} median 3M" for c in C.CAP_ORDER]
c2.plotly_chart(charts.lines(cap, f"Large vs small participation — {names[focus]}", "%"))
st.caption("Month-end points reconstructed from price history. Large/Mid/Small/Micro use the current market-cap category.")
