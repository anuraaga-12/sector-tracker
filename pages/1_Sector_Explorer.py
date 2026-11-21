"""Sector Explorer — sector profile, sub-sector breakdown and drill-down."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import config

C.setup("Sector Explorer", "🏭")
C.hero("Sector Explorer", "What each industry does, how its themes are performing, and how broad the move is.", icon="🏭")

secs = C.sectors()
ids = secs["sector_id"].tolist()
names = dict(zip(secs["sector_id"], secs["sector_name"]))
sid = st.selectbox("Sector", ids, index=C.pick_index(ids, st.session_state.get("sector_id")),
                   format_func=lambda x: f"{names[x]}  (Priority {int(secs.set_index('sector_id').loc[x, 'priority'])})")
st.session_state["sector_id"] = sid
s = secs.set_index("sector_id").loc[sid]

subs = C.subsectors()
subs = subs[subs["sector_id"] == sid]
sp = C.perf("subsector")
sp = sp[sp["sector_id"] == sid]
secp = C.perf("sector").set_index("entity_id")
row = secp.loc[sid] if sid in secp.index else None
cls = C.classifications()
comp = C.companies().set_index("company_id")
inc = config.settings()["membership"]["include_types"]
mem = cls[(cls["sector_id"] == sid) & cls["classification_type"].isin(inc)]

st.markdown(s["description"])
st.markdown("**Value chain**")
st.markdown(C.chain_html([x.strip() for x in str(s["value_chain"]).split("→")]), unsafe_allow_html=True)

m = st.columns(6)
m[0].metric("Sub-sectors", len(subs))
m[1].metric("Companies", mem["company_id"].nunique())
if row is not None:
    m[2].metric("Momentum rank", f"#{int(row['rank'])}" if pd.notna(row["rank"]) else "—",
                help="Rank among all sectors by the composite momentum score")
    m[3].metric("EW return 3M", C.pct(row["ew_3m"]), C.pct(row["xs500_3m"]) + " vs N500")
    m[4].metric("EW return 1Y", C.pct(row["ew_1y"]), C.pct(row["xs500_1y"]) + " vs N500")
    m[5].metric("% above 200-DMA", C.num(row["pct_above_200dma"]) + "%")
    if row.get("flags"):
        st.markdown(C.tags(str(row["flags"]).split("|"), "flag"), unsafe_allow_html=True)

st.divider()
st.subheader("Sub-sectors")
counts = mem.groupby("subsector_id")["company_id"].nunique()
caps = mem.merge(comp[["market_cap_category"]], left_on="company_id", right_index=True, how="left")
caps["market_cap_category"] = caps["market_cap_category"].fillna("Unknown")
tbl = subs[["subsector_id", "subsector_name", "value_chain_position"]].merge(
    sp.drop(columns=["name", "sector_id", "sector_name"], errors="ignore"), left_on="subsector_id", right_on="entity_id", how="left")
tbl["companies"] = tbl["subsector_id"].map(counts).fillna(0).astype(int)
tbl = tbl.sort_values("momentum_score", ascending=False, na_position="last")
show = ["subsector_name", "companies", "n_priced", "ew_1m", "ew_3m", "ew_6m", "ew_1y", "xs500_3m", "med_3m",
        "pct_outperf_3m", "pct_above_50dma", "momentum_score", "flags"]
d = C.as_pct_cols(tbl[show], ["ew_1m", "ew_3m", "ew_6m", "ew_1y", "xs500_3m", "med_3m"])
st.dataframe(d, hide_index=True, column_config={
    "subsector_name": "Sub-sector", "companies": "Companies", "n_priced": "Priced",
    "ew_1m": C.pct_col("1M"), "ew_3m": C.pct_col("3M"), "ew_6m": C.pct_col("6M"), "ew_1y": C.pct_col("1Y"),
    "xs500_3m": C.pct_col("vs N500 3M"), "med_3m": C.pct_col("Median 3M"),
    "pct_outperf_3m": st.column_config.NumberColumn("% beating N500", format="%.0f%%"),
    "pct_above_50dma": st.column_config.NumberColumn("% > 50DMA", format="%.0f%%"),
    "momentum_score": C.score_col(), "flags": "Signals"})
st.caption("Returns are equal-weighted sub-sector indices of primary + secondary constituents. Sub-sectors with fewer "
           "priced members than the ranking minimum are shown but not scored.")

c1, c2 = st.columns(2)
with c1:
    b = tbl[["subsector_name", "ew_3m"]].assign(ew_3m=tbl["ew_3m"] * 100)
    st.plotly_chart(charts.bar(b, "ew_3m", "subsector_name", title="3M equal-weighted return"), theme=None)
with c2:
    pv = caps.pivot_table(index="subsector_id", columns="market_cap_category", values="company_id", aggfunc="nunique", fill_value=0)
    pv = pv.reindex(columns=[c for c in C.CAP_ORDER + ["Unknown"] if c in pv.columns])
    pv.index = pv.index.map(subs.set_index("subsector_id")["subsector_name"])
    pv = pv.reindex([n for n in tbl["subsector_name"] if n in pv.index])
    st.plotly_chart(charts.stacked_caps(pv, "subsector", "Market-cap distribution (company count)", C.CAP_COLORS), theme=None)

st.subheader("Structural growth drivers & key risks")
drv, rsk = {}, {}
for p, n in zip(subs["profile"], subs["subsector_name"]):
    for x in p.get("drivers", []):
        drv.setdefault(x, []).append(n)
    for x in p.get("risks", []):
        rsk.setdefault(x, []).append(n)
c3, c4 = st.columns(2)
with c3:
    st.markdown("**Drivers** (sub-sectors citing them)")
    for k, v in sorted(drv.items(), key=lambda kv: -len(kv[1]))[:15]:
        st.markdown(f"- {k} <span class='small'>· {', '.join(v[:4])}{' …' if len(v) > 4 else ''}</span>", unsafe_allow_html=True)
with c4:
    st.markdown("**Risks**")
    for k, v in sorted(rsk.items(), key=lambda kv: -len(kv[1]))[:15]:
        st.markdown(f"- {k} <span class='small'>· {', '.join(v[:4])}{' …' if len(v) > 4 else ''}</span>", unsafe_allow_html=True)
st.caption("Drivers are an initial qualitative assessment; each sub-sector page separates structural from cyclical demand.")

st.divider()
idx = C.index_series("sector", sid)
if not idx.empty:
    bench = C.benchmarks()
    n500 = config.settings()["benchmarks"]["nifty500"]
    per = st.radio("Window", ["3M", "6M", "1Y", "3Y", "5Y"], index=2, horizontal=True, key="sec_win")
    start = idx.index.max() - pd.DateOffset(months={"3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60}[per])
    series = {"Equal-weighted": idx.get("ew"), "Cap-weighted": idx.get("cw")}
    if n500 in bench:
        series["Nifty 500"] = bench[n500]
    if pd.notna(s["benchmark"]) and s["benchmark"] in bench and s["benchmark"] != n500:
        series[f"Sector index ({s['benchmark']})"] = bench[s["benchmark"]]
    st.plotly_chart(charts.rebased_lines({k: v for k, v in series.items() if v is not None}, f"{s['sector_name']} vs benchmarks", start), theme=None)

st.markdown("#### Drill down")
opts = tbl["subsector_id"].tolist()
sub_names = dict(zip(subs["subsector_id"], subs["subsector_name"]))
pick = st.selectbox("Open sub-sector deep dive", opts, index=None, format_func=lambda x: sub_names[x], placeholder="Choose…")
if pick:
    C.goto("subsector", subsector_id=pick)
