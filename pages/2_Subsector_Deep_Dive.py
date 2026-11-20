"""Sub-sector Deep Dive — the core page: industry profile, full company universe, performance, peers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import config

C.setup("Sub-sector Deep Dive", "🔬")
st.title("🔬 Sub-sector Deep Dive")

subs = C.subsectors()
ids = subs["subsector_id"].tolist()
label = dict(zip(subs["subsector_id"], subs["sector_name"] + " › " + subs["subsector_name"]))
sid = st.selectbox("Sub-sector", ids, index=C.pick_index(ids, st.session_state.get("subsector_id")),
                   format_func=lambda x: label[x])
st.session_state["subsector_id"] = sid
info = subs.set_index("subsector_id").loc[sid]
prof = info["profile"]
sector_id = info["sector_id"]
st.session_state["sector_id"] = sector_id

perf_all = C.perf("subsector")
perf = perf_all.set_index("entity_id")
p = perf.loc[sid] if sid in perf.index else None
siblings = perf_all[(perf_all["sector_id"] == sector_id) & (perf_all["eligible"] == 1)].sort_values("momentum_score", ascending=False)
rank_in_sector = (siblings["entity_id"].tolist().index(sid) + 1) if sid in siblings["entity_id"].tolist() else None

cls = C.classifications()
comp = C.companies()
fund = C.fundamentals()
members = cls[cls["subsector_id"] == sid].merge(
    comp.drop(columns=["company_name", "nse_symbol"]), on="company_id", how="left")
type_order = {"primary": 0, "secondary": 1, "indirect": 2}
members = members.assign(_t=members["classification_type"].map(type_order)).sort_values(
    ["_t", "market_cap_cr"], ascending=[True, False])

# --------------------------------------------------------------------------- header
st.markdown(f"### {info['subsector_name']}  <span class='small'>· {info['sector_name']}</span>", unsafe_allow_html=True)
st.markdown(info["description"])
h = st.columns(6)
h[0].metric("Companies", members["company_id"].nunique(),
            help="All mapped companies incl. indirect exposure. Performance uses primary + secondary only.")
if p is not None:
    h[1].metric("Rank in sector", f"#{rank_in_sector} of {len(siblings)}" if rank_in_sector else "not ranked")
    h[2].metric("Momentum score", C.num(p["momentum_score"]), help="0-100 composite; see Methodology")
    h[3].metric("EW return 3M", C.pct(p["ew_3m"]), C.pct(p["xs500_3m"]) + " vs N500")
    h[4].metric("Median stock 3M", C.pct(p["med_3m"]))
    h[5].metric("% above 50 / 200 DMA", f"{C.num(p['pct_above_50dma'])}% / {C.num(p['pct_above_200dma'])}%")
    if p.get("flags"):
        st.markdown(C.tags(str(p["flags"]).split("|"), "flag"), unsafe_allow_html=True)

tab_o, tab_c, tab_p, tab_f, tab_v = st.tabs(["Industry overview", "Company universe", "Market performance",
                                             "Peer comparison", "Value chain"])

# --------------------------------------------------------------------------- overview
with tab_o:
    a, b = st.columns([3, 2])
    with a:
        def para(t, k):
            v = prof.get(k)
            if v:
                st.markdown(f"**{t}.** {v}")
        st.markdown(f"**Position in value chain.** {info['value_chain_position'] or '—'}")
        para("Customers", "customers")
        para("Key inputs", "inputs")
        para("Economics & profitability", "economics")
        para("Entry barriers & what separates leaders", "barriers")
        st.markdown("**Structural growth drivers**")
        for d_ in prof.get("drivers", []):
            st.markdown(f"- {d_}")
        if prof.get("nature"):
            st.info(f"**Structural vs cyclical:** {prof['nature']}")
        st.markdown("**Key risks**")
        for r_ in prof.get("risks", []):
            st.markdown(f"- {r_}")
    with b:
        st.markdown("**Industry attractiveness** (qualitative)")
        rt = C.ratings_table(prof)
        if rt.empty:
            st.caption("Not yet assessed.")
        else:
            st.dataframe(rt, hide_index=True)
        st.caption("🟢 favourable · 🟡 neutral · 🔴 unfavourable · ⚪ context. Initial analyst view — not derived from "
                   "price data. Strong structural ratings do not imply good near-term stock performance.")

# --------------------------------------------------------------------------- universe
with tab_c:
    f1, f2, f3 = st.columns(3)
    types = f1.multiselect("Exposure type", ["primary", "secondary", "indirect"], default=["primary", "secondary", "indirect"],
                           format_func=C.TYPE_LABEL.get)
    caps = f2.multiselect("Market-cap category", C.CAP_ORDER + ["Unknown"], default=C.CAP_ORDER + ["Unknown"])
    conf = f3.multiselect("Classification confidence", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    mm = members.copy()
    mm["market_cap_category"] = mm["market_cap_category"].fillna("Unknown")
    mm = mm[mm["classification_type"].isin(types) & mm["market_cap_category"].isin(caps)
            & mm["classification_confidence"].isin(conf)]
    pure = members[(members["classification_type"] == "primary") & members["revenue_exposure"].fillna("").str.startswith("Pure")]
    k = st.columns(5)
    k[0].metric("Pure-play", len(pure))
    k[1].metric("Primary (diversified)", int((members["classification_type"] == "primary").sum() - len(pure)))
    k[2].metric("Secondary", int((members["classification_type"] == "secondary").sum()))
    k[3].metric("Indirect", int((members["classification_type"] == "indirect").sum()))
    k[4].metric("Small + Micro", int(members["market_cap_category"].isin(["Small", "Micro"]).sum()))
    show = mm[["company_name", "nse_symbol", "classification_type", "revenue_exposure", "market_cap_category", "market_cap_cr",
               "market_position", "business_model", "primary_business", "customer_industry", "classification_confidence",
               "last_close", "return_3m", "return_1y", "pct_from_52w_high"]].copy()
    show["classification_type"] = show["classification_type"].map(C.TYPE_LABEL)
    show = C.as_pct_cols(show, ["return_3m", "return_1y", "pct_from_52w_high"])
    st.dataframe(show, hide_index=True, height=min(640, 38 * len(show) + 40), column_config={
        "company_name": st.column_config.TextColumn("Company", width="medium"), "nse_symbol": "NSE",
        "classification_type": "Exposure", "revenue_exposure": "Exposure estimate", "market_cap_category": "Cap",
        "market_cap_cr": st.column_config.NumberColumn("Mcap (₹ cr)", format="localized"), "market_position": "Position",
        "business_model": "Model", "primary_business": st.column_config.TextColumn("What it does", width="large"),
        "customer_industry": "Customers", "classification_confidence": "Confidence",
        "last_close": st.column_config.NumberColumn("Price", format="%.2f"),
        "return_3m": C.pct_col("3M"), "return_1y": C.pct_col("1Y"), "pct_from_52w_high": C.pct_col("From 52W high")})
    st.caption("Exposure estimates are analyst bands, not reported segment figures. 'Secondary' = material but not the "
               "main business; 'Indirect' = minor exposure, excluded from performance maths. Source for every mapping: "
               "see Company Explorer.")
    c_open = st.selectbox("Open company", mm["nse_symbol"].tolist(), index=None, placeholder="Choose company…",
                          format_func=lambda x: f"{mm.set_index('nse_symbol').loc[x, 'company_name']} ({x})")
    if c_open:
        C.goto("company", symbol=c_open)

# --------------------------------------------------------------------------- performance
with tab_p:
    if p is None or pd.isna(p.get("n_priced")) or p["n_priced"] == 0:
        st.info("No price data for this sub-sector yet.")
    else:
        periods = ["1w", "1m", "3m", "6m", "1y", "3y", "5y"]
        cfgb = config.settings()["benchmarks"]
        bench = C.benchmarks()
        from tracker.analytics import series_return
        rows = {"Equal-weighted": [p[f"ew_{x}"] for x in periods], "Cap-weighted": [p[f"cw_{x}"] for x in periods],
                "Median stock": [p[f"med_{x}"] for x in periods], "Excess vs Nifty 500 (EW)": [p[f"xs500_{x}"] for x in periods]}
        for lab, t in (("Nifty 500", cfgb["nifty500"]), ("Nifty 50", cfgb["nifty50"])):
            if t in bench:
                s = bench[t].dropna()
                rows[lab] = [series_return(s, len(s) - 1, x) for x in periods]
        rt = pd.DataFrame(rows, index=[C.PERIOD_LABEL[x] for x in periods]).T * 100
        st.dataframe(rt, column_config={c: C.pct_col(c) for c in rt.columns})
        win = st.radio("Chart window", ["3M", "6M", "1Y", "3Y", "5Y"], index=2, horizontal=True)
        idx = C.index_series("subsector", sid)
        if not idx.empty:
            start = idx.index.max() - pd.DateOffset(months={"3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60}[win])
            ser = {"Equal-weighted": idx.get("ew"), "Cap-weighted": idx.get("cw")}
            if cfgb["nifty500"] in bench:
                ser["Nifty 500"] = bench[cfgb["nifty500"]]
            st.plotly_chart(charts.rebased_lines({k_: v for k_, v in ser.items() if v is not None},
                                                 f"{info['subsector_name']} vs Nifty 500", start))
        b1, b2 = st.columns(2)
        with b1:
            st.markdown("**Breadth**")
            br = pd.DataFrame({"Metric": ["Constituents (priced)", "Positive 3M", "Beating Nifty 500 · 1M",
                                          "Beating Nifty 500 · 3M", "Beating Nifty 500 · 6M", "Above 50-DMA", "Above 200-DMA",
                                          "Top-2 share of cap-weighted 3M gain"],
                               "Value": [f"{int(p['n_priced'])} of {int(p['n_members'])}", f"{C.num(p['pct_positive_3m'])}%",
                                         f"{C.num(p['pct_outperf_1m'])}%", f"{C.num(p['pct_outperf_3m'])}%",
                                         f"{C.num(p['pct_outperf_6m'])}%", f"{C.num(p['pct_above_50dma'])}%",
                                         f"{C.num(p['pct_above_200dma'])}%", f"{C.num(p['top2_share_3m'])}%"]})
            st.dataframe(br, hide_index=True)
            gap = (p["cw_3m"] - p["med_3m"]) * 100 if pd.notna(p["cw_3m"]) and pd.notna(p["med_3m"]) else np.nan
            if pd.notna(gap):
                verdict = ("Move is concentrated in heavyweights" if gap >= config.settings()["rotation"]["narrow_gap_pp"]
                           else "Smaller names are outperforming the heavyweights" if gap <= -5 else "Move is reasonably broad-based")
                st.markdown(f"Cap-weighted minus median 3M return: **{gap:+.1f} pp** → {verdict}.")
        with b2:
            capm = pd.DataFrame({"Category": C.CAP_ORDER, "Median 3M": [p.get(f"med_3m_{c.lower()}") for c in C.CAP_ORDER]})
            capm["Median 3M"] = capm["Median 3M"] * 100
            st.plotly_chart(charts.bar(capm, "Median 3M", "Category", "Median 3M return by market-cap category", height=260))
            labels = {"c_relative": "Relative performance", "c_absolute": "Absolute performance",
                      "c_consistency": "Consistency across periods", "c_breadth": "Breadth (% beating N500)",
                      "c_ma_breadth": "% above moving averages"}
            if pd.notna(p.get("momentum_score")):
                st.plotly_chart(charts.components_bar(p, labels))
        per = st.radio("Constituent returns", ["1M", "3M", "6M", "1Y"], index=1, horizontal=True)
        col = f"return_{per.lower()}"
        perf_m = members[members["classification_type"] != "indirect"][["company_name", col, "market_cap_category"]].dropna(subset=[col])
        perf_m[col] = perf_m[col] * 100
        perf_m["market_cap_category"] = perf_m["market_cap_category"].fillna("Unknown")
        st.plotly_chart(charts.bar(perf_m.sort_values(col, ascending=False), col, "company_name",
                                   f"{per} return by constituent (colour = market-cap category)", color="market_cap_category",
                                   color_map=C.CAP_COLORS))

# --------------------------------------------------------------------------- peers
with tab_f:
    f = fund[fund["company_id"].isin(members["company_id"])]
    peers = members[["company_id", "company_name", "nse_symbol", "classification_type", "market_cap_category", "market_cap_cr"]].merge(
        f.drop(columns=["nse_symbol"]), on="company_id", how="left")
    if f.empty:
        st.info("No fundamental data loaded yet. Run `python -m tracker.refresh fundamentals` (weekly job) or add "
                "`data/manual/fundamentals_override.csv`.")
    cols = ["company_name", "classification_type", "market_cap_category", "market_cap_cr", "revenue", "revenue_growth", "pat_growth",
            "ebitda_margin", "roce", "roe", "debt_to_equity", "pe", "pb", "ev_ebitda", "reporting_period", "source_reference", "as_of"]
    pv = C.as_pct_cols(peers[[c for c in cols if c in peers]], ["revenue_growth", "pat_growth", "ebitda_margin", "roce", "roe"])
    pv["classification_type"] = pv["classification_type"].map(C.TYPE_LABEL)
    st.dataframe(pv, hide_index=True, column_config={
        "company_name": "Company", "classification_type": "Exposure", "market_cap_category": "Cap",
        "market_cap_cr": st.column_config.NumberColumn("Mcap ₹ cr", format="localized"),
        "revenue": st.column_config.NumberColumn("Revenue ₹ cr", format="localized"),
        "revenue_growth": C.pct_col("Sales growth"), "pat_growth": C.pct_col("Profit growth"),
        "ebitda_margin": C.pct_col("EBITDA margin"), "roce": C.pct_col("ROCE"), "roe": C.pct_col("ROE"),
        "debt_to_equity": st.column_config.NumberColumn("D/E", format="%.2f"),
        "pe": st.column_config.NumberColumn("P/E", format="%.1f"), "pb": st.column_config.NumberColumn("P/B", format="%.1f"),
        "ev_ebitda": st.column_config.NumberColumn("EV/EBITDA", format="%.1f"),
        "reporting_period": "Period", "source_reference": "Source", "as_of": "As of"})
    st.caption("Shown only where a provider returned data. Yahoo's summary mixes TTM figures with latest-quarter YoY growth — "
               "always check the period and source columns. Blank = unavailable, never estimated.")
    if not f.empty and peers["roce"].notna().sum() >= 3:
        sc = peers.assign(roce_pct=peers["roce"] * 100)
        st.plotly_chart(charts.scatter(sc, "roce_pct", "pe", "market_cap_cr", "nse_symbol", "market_cap_category",
                                       "ROCE (%) vs P/E · bubble = market cap", C.CAP_COLORS))

# --------------------------------------------------------------------------- value chain
with tab_v:
    sec = C.sectors().set_index("sector_id").loc[sector_id]
    st.markdown(f"**{sec['sector_name']} value chain**")
    st.markdown(C.chain_html([x.strip() for x in str(sec["value_chain"]).split("→")]), unsafe_allow_html=True)
    sib = subs[subs["sector_id"] == sector_id][["subsector_id", "subsector_name", "value_chain_position"]].copy()
    cnt = cls[cls["classification_type"].isin(["primary", "secondary"])].groupby("subsector_id")["company_id"].nunique()
    sib["companies"] = sib["subsector_id"].map(cnt).fillna(0).astype(int)
    sib["score"] = sib["subsector_id"].map(perf["momentum_score"])
    sib["this"] = np.where(sib["subsector_id"] == sid, "◀ this", "")
    st.dataframe(sib.drop(columns="subsector_id"), hide_index=True, column_config={
        "subsector_name": "Sub-sector", "value_chain_position": "Where it sits", "companies": "Companies",
        "score": C.score_col(), "this": ""})
    st.caption("Different stages of the same theme can have very different economics — compare the attractiveness "
               "ratings of upstream and downstream sub-sectors before treating a theme as one trade.")
