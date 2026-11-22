"""Fund Holdings — latest portfolios and performance of the largest small, mid and flexi cap funds."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import funds as F

C.setup("Fund Holdings", "💼")
D = C.mf_data()
meta, nav, hold, ref = D["funds"], D["nav"], D["holdings"], D["ref"]

latest_hold = hold["as_of"].max() if not hold.empty else None
C.hero("Mutual Fund Holdings",
       "What the largest small, mid and flexi cap funds own, what they bought and sold last month, and how they "
       "have performed against their index. Direct-plan NAVs; holdings from each fund house's monthly SEBI disclosure.",
       icon="💼",
       chips=[(f"🗂️ Holdings as of {C._fmt_date(latest_hold)}", "v") if latest_hold else ("🗂️ No holdings yet", "a"),
              (f"📈 NAV as of {C._fmt_date(nav.index.max())}", "") if not nav.empty else ("📈 No NAVs yet", "a"),
              (f"💼 {int((meta['role'] == 'fund').sum())} funds · 3 categories", "")])

if nav.empty and hold.empty:
    st.info("No mutual-fund data yet. It is downloaded by the daily refresh (`python -m tracker.refresh funds`).")
    st.stop()

# --------------------------------------------------------------------------- category
cats = list(dict.fromkeys(meta["category"]))
cat = st.radio("Fund category", cats, horizontal=True, label_visibility="collapsed")
m = meta[meta["category"] == cat]
bench_row = m[m["role"] == "benchmark"]
bench_code = bench_row["amfi"].iloc[0] if not bench_row.empty else None
bench_name = bench_row["name"].iloc[0].replace(" (index fund)", "") if not bench_row.empty else "index"
fm = m[m["role"] == "fund"].copy()
codes = fm["amfi"].tolist()
names = dict(zip(meta["amfi"], meta["name"]))

# Per-fund snapshot from the latest disclosure: AUM, number of stocks, top-10 weight, cash
snap = []
for c in codes:
    h = hold[hold["amfi"] == c]
    if h.empty:
        snap.append({"amfi": c})
        continue
    a = h["as_of"].max()
    h = F.classify_rows(h[h["as_of"] == a], ref)
    st_rows = h[h["bucket"].isin(["Indian stock", "Foreign stock"])]
    snap.append({"amfi": c, "as_of": a, "aum_cr": h["value_cr"].sum(), "n_stocks": len(st_rows),
                 "top10": st_rows.nlargest(10, "pct_nav")["pct_nav"].sum(),
                 "cash": h.loc[h["bucket"] == "Cash & debt", "pct_nav"].sum()})
snap = pd.DataFrame(snap).set_index("amfi")
rets = F.nav_returns(nav[[c for c in codes + ([bench_code] if bench_code else []) if c in nav.columns]])
perf = fm.set_index("amfi")[["name", "fund_house"]].join(snap).join(rets)
perf = perf.sort_values("aum_cr", ascending=False, na_position="last")
order = perf.index.tolist()
bench_ret = rets.loc[bench_code] if bench_code in rets.index else pd.Series(dtype=float)

tab_perf, tab_hold, tab_flow = st.tabs(["📈 Performance", "🗂️ Fund holdings", "🔁 Buying & selling"])

# =========================================================================== performance
with tab_perf:
    beat = int((perf["1y"] > bench_ret.get("1y", np.nan)).sum())
    k = st.columns(4)
    k[0].metric(f"{cat} AUM tracked", C.crore(perf["aum_cr"].sum()), help="Sum of the funds' month-end portfolio values.")
    k[1].metric(f"Beat {bench_name} · 1Y", f"{beat} of {perf['1y'].notna().sum()}")
    k[2].metric("Median fund · 1Y", C.pct(perf["1y"].median()), help=f"{bench_name}: {C.pct(bench_ret.get('1y'))}")
    k[3].metric("Median fund · 3Y CAGR", C.pct(perf["3y"].median()), help=f"{bench_name}: {C.pct(bench_ret.get('3y'))}")

    tbl = perf.copy()
    if not bench_ret.empty:
        b = bench_ret.to_frame().T
        b.index = [bench_code]
        b["name"] = f"📏 {bench_name} index"
        tbl = pd.concat([b, tbl])
    num_cols = ["aum_cr", "nav", *F.NAV_PERIODS, "n_stocks", "top10", "cash"]
    tbl[num_cols] = tbl[num_cols].apply(pd.to_numeric, errors="coerce").astype(float)
    tbl = C.as_pct_cols(tbl.reset_index(drop=True), list(F.NAV_PERIODS))
    st.dataframe(
        tbl[["name", "aum_cr", "nav", *F.NAV_PERIODS, "n_stocks", "top10", "cash"]], hide_index=True,
        height=min(560, 36 * len(tbl) + 40),
        column_config={"name": st.column_config.TextColumn("Fund", width="medium"),
                       "aum_cr": st.column_config.NumberColumn("AUM ₹ cr", format="%,.0f",
                                                               help="Month-end portfolio value from the latest disclosure."),
                       "nav": st.column_config.NumberColumn("NAV ₹", format="%.2f"),
                       **{p: C.pct_col(C.PERIOD_LABEL[p]) for p in F.NAV_PERIODS},
                       "n_stocks": st.column_config.NumberColumn("Stocks", format="%d"),
                       "top10": st.column_config.NumberColumn("Top 10 %", format="%.1f%%",
                                                              help="Weight of the ten largest stock positions."),
                       "cash": st.column_config.NumberColumn("Cash & debt %", format="%.1f%%")})
    st.caption(f"Direct plan, growth option. 3Y / 5Y are annualised. 📏 = {names.get(bench_code, bench_name)}, a "
               "low-cost index fund used as the benchmark (it is after its own small expense ratio, like the funds).")

    c1, c2 = st.columns([5, 6], gap="medium")
    with c1:
        per = st.radio("Return period", list(F.NAV_PERIODS), index=3, horizontal=True,
                       format_func=lambda p: p.upper(), key="mf_per")
        d = perf.assign(r=perf[per] * 100)
        st.plotly_chart(charts.returns_vs_bench(d, "r", "name", bench_ret.get(per, np.nan) * 100, bench_name,
                                                f"{C.PERIOD_LABEL[per]} return vs {bench_name}"), theme=None)
        st.caption("3Y and 5Y bars are annualised (CAGR).")
    with c2:
        span = st.radio("Chart period", ["1Y", "3Y", "5Y"], index=1, horizontal=True, key="mf_span")
        pick = st.multiselect("Funds to plot (up to 7)", order, default=order[:5], format_func=names.get,
                              max_selections=7, key=f"mf_pick_{cat}")
        start = nav.index.max() - pd.DateOffset(years=int(span[0]))
        ser = {names[c]: nav[c] for c in pick if c in nav}
        if bench_code in nav:
            ser = {bench_name: nav[bench_code], **ser}
        # rebase every line from the first date where all of them have a NAV
        common = max([s.dropna().index.min() for s in ser.values()] + [start]) if ser else start
        st.plotly_chart(charts.rebased_lines(ser, f"Growth of ₹100 since {C._fmt_date(common)}", start=common,
                                             reference=bench_name), theme=None)

# =========================================================================== single-fund holdings
with tab_hold:
    have = [c for c in order if c in set(hold["amfi"])]
    if not have:
        st.info("No holdings disclosed yet for these funds.")
    else:
        fund = st.selectbox("Fund", have, format_func=names.get, key=f"mf_fund_{cat}")
        pos, cur_m, prev_m = F.stock_positions(hold, fund, ref)
        cls = C.classifications()
        prim = cls[cls["classification_type"] == "primary"].drop_duplicates("nse_symbol").set_index("nse_symbol")
        pos["tracker_sector"] = pos["symbol"].map(prim["sector_name"])
        pos["tracker_sub"] = pos["symbol"].map(prim["subsector_name"])
        live = pos[pos["status"] != "Exited"]
        s = snap.loc[fund]
        k = st.columns(5)
        k[0].metric("AUM", C.crore(s.get("aum_cr")))
        k[1].metric("Stocks held", int(s.get("n_stocks", 0) or 0))
        k[2].metric("Top 10 weight", f"{s.get('top10', np.nan):.1f}%")
        k[3].metric("Cash & debt", f"{s.get('cash', np.nan):.1f}%")
        n_new, n_exit = int((pos["status"] == "New").sum()), int((pos["status"] == "Exited").sum())
        k[4].metric("New buys · exits", f"{n_new} · {n_exit}", help=f"{C._fmt_date(cur_m)} vs {C._fmt_date(prev_m)}")

        c1, c2 = st.columns(2, gap="medium")
        mix = F.asset_mix(hold, fund, cur_m, ref)
        mix_order = ["Large cap", "Mid cap", "Small cap", "Other Indian equity", "Foreign stock", "REIT / InvIT",
                     "Cash & debt", "Derivatives", "Other"]
        mix = mix.reindex([x for x in mix_order if x in mix.index])
        mix = mix[mix.abs() >= 0.05]
        c1.plotly_chart(charts.hbar(pd.DataFrame({"b": mix.index, "w": mix.values}), "w", "b", "Portfolio mix · % of NAV",
                                    color=charts.BLUE), theme=None)
        ind = live.groupby(live["industry"].fillna("Other"))["pct_nav"].sum().nlargest(12).rename("w").reset_index()
        c2.plotly_chart(charts.hbar(ind, "w", "industry", "Top industries · % of NAV"), theme=None)
        st.caption("Large cap = Nifty 100, Mid cap = Nifty Midcap 150, Small cap = other NSE-listed stocks (current "
                   "index membership — close to, but not the same as, AMFI's half-yearly list).")

        if prev_m:
            def _rows(df, val):
                return [{"rank": i, "name": r.instrument, "sub": f"{r.industry or ''}",
                         "value": val(r), "tone": "up" if r.status in ("New", "Added") else "dn"}
                        for i, r in enumerate(df.itertuples(), 1)]
            buys = pos[pos["status"] == "New"].nlargest(6, "pct_nav")
            sells = pos[pos["status"] == "Exited"].nlargest(6, "prev_pct")
            adds = pos[pos["status"] == "Added"].assign(d=lambda x: x["pct_nav"] - x["prev_pct"]).nlargest(6, "d")
            trims = pos[pos["status"] == "Trimmed"].assign(d=lambda x: x["pct_nav"] - x["prev_pct"]).nsmallest(6, "d")
            cards = [
                C.list_card(f"New positions · {pd.Timestamp(cur_m):%b %Y}", _rows(buys, lambda r: f"{r.pct_nav:.2f}%"),
                            icon="🆕", accent="g", empty="No new stocks this month."),
                C.list_card("Fully exited", _rows(sells, lambda r: f"was {r.prev_pct:.2f}%"),
                            icon="🚪", accent="r", empty="No exits this month."),
                C.list_card("Biggest additions", _rows(adds, lambda r: f"{r.prev_pct:.2f}→{r.pct_nav:.2f}%"),
                            icon="➕", accent="v", empty="No meaningful additions."),
                C.list_card("Biggest reductions", _rows(trims, lambda r: f"{r.prev_pct:.2f}→{r.pct_nav:.2f}%"),
                            icon="➖", accent="a", empty="No meaningful reductions."),
            ]
            for pair in (cards[:2], cards[2:]):
                for col, html in zip(st.columns(2, gap="medium"), pair):
                    col.markdown(html, unsafe_allow_html=True)
                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        st.markdown(f"#### All holdings · {names[fund]} · {C._fmt_date(cur_m)}")
        q = st.text_input("Search holdings", "", placeholder="Company, symbol or industry", key="mf_q")
        t = pos.copy()
        t["d_pct"] = t["pct_nav"] - t["prev_pct"]
        t["qty_change"] = t["qty_change"] * 100
        if q:
            hay = (t["instrument"].fillna("") + " " + t["symbol"].fillna("") + " " + t["industry"].fillna("")).str.lower()
            t = t[hay.str.contains(q.lower(), regex=False)]
        t["tracker_sector"] = t["tracker_sector"].fillna("—")
        st.dataframe(
            t[["instrument", "symbol", "pct_nav", "d_pct", "status", "qty_change", "value_cr", "size", "industry",
               "tracker_sector"]], hide_index=True, height=min(640, 36 * len(t) + 40),
            column_config={
                "instrument": st.column_config.TextColumn("Company", width="medium"),
                "symbol": st.column_config.TextColumn("NSE"),
                "pct_nav": st.column_config.ProgressColumn("% of NAV", min_value=0, width="small",
                                                           max_value=float(max(t["pct_nav"].max(), 1)) if len(t) else 10,
                                                           format="%.2f%%"),
                "d_pct": st.column_config.NumberColumn("Δ wt (pp)", format="%+.2f", width="small",
                                                       help="Change in % of NAV vs the previous month (includes price moves)."),
                "status": st.column_config.TextColumn("Activity", width="small",
                                                      help="From the change in shares held: New, Added (> +2%), Trimmed "
                                                           "(< −2%), Held, Exited. Splits / bonus issues are adjusted."),
                "qty_change": st.column_config.NumberColumn("Shares Δ", format="%+.0f%%", width="small"),
                "value_cr": st.column_config.NumberColumn("Value ₹ cr", format="%,.1f", width="small"),
                "size": st.column_config.TextColumn("Size", width="small"),
                "industry": st.column_config.TextColumn("Industry (AMFI)", width="medium"),
                "tracker_sector": st.column_config.TextColumn("Sector (tracker)", width="medium")})
        st.download_button("⬇️ Download holdings (CSV)", pos.to_csv(index=False).encode(),
                           file_name=f"{names[fund].replace(' ', '_')}_{cur_m}.csv", mime="text/csv")

# =========================================================================== across the category
with tab_flow:
    g, latest = F.category_flows(hold, codes, ref)
    if g.empty:
        st.info("No holdings disclosed yet for these funds.")
    else:
        n_f = hold.loc[hold["amfi"].isin(codes) & (hold["as_of"] == latest), "amfi"].nunique()
        st.markdown(f"What the {n_f} tracked **{cat.lower()}** funds did in **{pd.Timestamp(latest):%B %Y}** "
                    "(latest disclosure vs the month before). Money in / out is estimated as the change in shares × "
                    "the month-end price.")

        def _flow_rows(df):
            out = []
            for i, r in enumerate(df.itertuples(), 1):
                bits = [f"{r.funds} fund{'s' if r.funds != 1 else ''} hold"] if r.funds else []
                if r.new:
                    bits.append(f"{r.new} new")
                if r.added:
                    bits.append(f"{r.added} added")
                if r.trimmed:
                    bits.append(f"{r.trimmed} trimmed")
                if r.exited:
                    bits.append(f"{r.exited} exited")
                out.append({"rank": i, "name": r.instrument, "sub": " · ".join(bits),
                            "value": f"{'+' if r.net_value_cr > 0 else '−'}₹{abs(r.net_value_cr):,.0f} cr",
                            "tone": "up" if r.net_value_cr > 0 else "dn"})
            return out

        bought = g[g["net_value_cr"] > 0].nlargest(8, "net_value_cr")
        sold = g[g["net_value_cr"] < 0].nsmallest(8, "net_value_cr")
        c1, c2 = st.columns(2, gap="medium")
        c1.markdown(C.list_card("Most bought (₹, net)", _flow_rows(bought), icon="🟢", accent="g"), unsafe_allow_html=True)
        c2.markdown(C.list_card("Most sold (₹, net)", _flow_rows(sold), icon="🔴", accent="r"), unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # Portfolio mix of every fund in the category, side by side
        mixes = {names[c]: F.asset_mix(hold, c, hold.loc[hold["amfi"] == c, "as_of"].max(), ref)
                 for c in order if c in set(hold["amfi"])}
        mx = pd.DataFrame(mixes).T.fillna(0)
        cols = [x for x in ["Large cap", "Mid cap", "Small cap", "Other Indian equity", "Foreign stock", "REIT / InvIT",
                            "Cash & debt", "Derivatives", "Other"] if x in mx.columns]
        colors = {"Large cap": charts.CAP_RAMP["Large"], "Mid cap": charts.CAP_RAMP["Mid"],
                  "Small cap": charts.CAP_RAMP["Micro"], "Other Indian equity": "#b9c7da", "Foreign stock": charts.PINK,
                  "REIT / InvIT": charts.YELLOW, "Cash & debt": charts.AQUA, "Derivatives": charts.GREY, "Other": "#dcdae6"}
        st.plotly_chart(charts.stacked_caps(mx[cols].clip(lower=0), "", "Portfolio mix by fund · % of NAV", colors),
                        theme=None)

        st.markdown("#### Most widely held stocks")
        top = g[g["funds"] > 0].sort_values(["funds", "value_cr"], ascending=False)
        def _act(r):
            parts = [f"{getattr(r, k)} {lab}" for k, lab in (("new", "new"), ("added", "added"), ("trimmed", "trimmed"),
                                                              ("exited", "exited")) if getattr(r, k)]
            return " · ".join(parts) or "no change"
        top = top.head(60).copy()
        top["activity"] = [_act(r) for r in top.itertuples()]
        st.dataframe(
            top[["instrument", "symbol", "industry", "funds", "avg_pct", "value_cr", "activity", "net_value_cr"]],
            hide_index=True, height=560,
            column_config={
                "instrument": st.column_config.TextColumn("Company", width="medium"),
                "symbol": st.column_config.TextColumn("NSE", width="small"), "industry": "Industry",
                "funds": st.column_config.ProgressColumn(f"Funds holding (of {n_f})", min_value=0, max_value=n_f, format="%d"),
                "avg_pct": st.column_config.NumberColumn("Avg weight", format="%.2f%%",
                                                         help="Average % of NAV among the funds that hold it."),
                "value_cr": st.column_config.NumberColumn("Held ₹ cr", format="%,.0f"),
                "activity": st.column_config.TextColumn("Last month (funds)", width="medium"),
                "net_value_cr": st.column_config.NumberColumn("Net bought ₹ cr", format="%+,.0f")})
        st.caption("Activity counts are funds. Quantity changes are adjusted for splits and bonus issues where detected.")

st.caption("Sources: NAVs from AMFI via mfapi.in (daily). Holdings from each fund house's SEBI-mandated monthly portfolio "
           "disclosure, parsed by the open fund-holdings-data project (published ~10 days after month-end). "
           "Past performance does not indicate future returns. Not investment advice.")
