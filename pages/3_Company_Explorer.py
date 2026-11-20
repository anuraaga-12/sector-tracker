"""Company Explorer — Screener-style company page with interactive price chart."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard import charts
from dashboard import common as C
from tracker import config

C.setup("Company Explorer", "🏢")
st.title("🏢 Company Explorer")

comp = C.companies()
cls = C.classifications()
fund = C.fundamentals()
opts = comp.sort_values("company_name")["nse_symbol"].tolist()
names = dict(zip(comp["nse_symbol"], comp["company_name"]))
sym = st.selectbox("Search company (name or NSE symbol)", opts, index=C.pick_index(opts, st.session_state.get("symbol")),
                   format_func=lambda x: f"{names[x]} ({x})")
st.session_state["symbol"] = sym
c = comp.set_index("nse_symbol").loc[sym]
mine = cls[cls["nse_symbol"] == sym].assign(_o=lambda d: d["classification_type"].map({"primary": 0, "secondary": 1, "indirect": 2})).sort_values("_o")
prim = mine[mine["classification_type"] == "primary"]
f = fund[fund["nse_symbol"] == sym]
f = f.iloc[0] if not f.empty else None

# --------------------------------------------------------------------------- header
st.markdown(f"## {c['company_name']}  <span class='small'>NSE: {sym}"
            f"{' · BSE: ' + str(c['bse_code']) if pd.notna(c['bse_code']) and c['bse_code'] else ''}"
            f"{' · ISIN: ' + str(c['isin']) if pd.notna(c['isin']) and c['isin'] else ''}"
            f" · {c['listing_status']}</span>", unsafe_allow_html=True)
tag_html = " ".join(
    f"<span class='tag {r.classification_type}'>{r.sector_name} › {r.subsector_name} · {C.TYPE_LABEL[r.classification_type]}</span>"
    for r in mine.itertuples())
st.markdown(tag_html, unsafe_allow_html=True)
st.markdown(f"**What it does:** {c['primary_business']}  \n**Customers:** {c['customer_industry']}  \n"
            f"**Market position:** {c['market_position']} · **Business model:** {c['business_model']}")
links = (f"[Screener.in](https://www.screener.in/company/{sym}/consolidated/) · "
         f"[NSE](https://www.nseindia.com/get-quotes/equity?symbol={sym}) · "
         f"[TradingView](https://www.tradingview.com/chart/?symbol=NSE:{sym})")
st.markdown(f"<span class='small'>Research links: </span>{links}", unsafe_allow_html=True)

# --------------------------------------------------------------------------- key ratios (Screener-like grid)
def _v(x, kind):
    if f is None and kind not in ("mcap", "price", "hi", "lo"):
        return "—"
    return {"pct": C.pct, "x": lambda v: C.num(v, 1), "mcap": C.crore, "price": lambda v: C.num(v, 2),
            "hi": lambda v: C.num(v, 2), "lo": lambda v: C.num(v, 2)}[kind](x)


g = st.columns(6)
g[0].metric("Market cap", C.crore(c["market_cap_cr"]), c["market_cap_category"] or "—",
            help=f"As of {c['market_cap_as_of'] or 'n/a'} · {c['market_cap_category_source'] or ''}")
g[1].metric("Price", C.num(c["last_close"], 2), C.pct(c["return_1w"]) + " 1W" if pd.notna(c["return_1w"]) else None,
            help=f"Close on {c['last_price_date'] or 'n/a'} (end-of-day, adjusted)")
g[2].metric("52W high / low", f"{C.num(c['high_52w'], 0)} / {C.num(c['low_52w'], 0)}",
            C.pct(c["pct_from_52w_high"]) + " from high" if pd.notna(c["pct_from_52w_high"]) else None)
g[3].metric("P/E · P/B", f"{_v(f['pe'] if f is not None else None, 'x')} · {_v(f['pb'] if f is not None else None, 'x')}")
g[4].metric("ROCE · ROE", f"{_v(f['roce'] if f is not None else None, 'pct')} · {_v(f['roe'] if f is not None else None, 'pct')}")
g[5].metric("Debt / Equity", _v(f["debt_to_equity"] if f is not None else None, "x"))
g2 = st.columns(6)
g2[0].metric("Sales growth", _v(f["revenue_growth"] if f is not None else None, "pct"))
g2[1].metric("Profit growth", _v(f["pat_growth"] if f is not None else None, "pct"))
g2[2].metric("EBITDA margin", _v(f["ebitda_margin"] if f is not None else None, "pct"))
g2[3].metric("Above 50 DMA", "Yes" if c["above_50dma"] == 1 else "No" if c["above_50dma"] == 0 else "—")
g2[4].metric("Above 200 DMA", "Yes" if c["above_200dma"] == 1 else "No" if c["above_200dma"] == 0 else "—")
g2[5].metric("Fundamentals as of", f["as_of"] if f is not None else "—")
if f is not None:
    st.caption(f"Fundamentals: {f['source_reference']} · period: {f['reporting_period']}. Blank = not available.")

# --------------------------------------------------------------------------- chart
st.divider()
st.subheader("Price chart")


@st.cache_data(ttl=3600, show_spinner="Fetching OHLCV …")
def live_ohlcv(ticker: str) -> pd.DataFrame:
    if config.DATA_MODE == "demo":
        return pd.DataFrame()
    try:
        from tracker.providers import yahoo
        return yahoo.download_ohlcv(ticker, period="max")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=6 * 3600, show_spinner="Fetching financial statements …")
def live_statements(ticker: str) -> dict:
    if config.DATA_MODE == "demo":
        return {}
    try:
        from tracker.providers import yahoo
        return yahoo.fetch_statements(ticker)
    except Exception:
        return {}


ctl = st.columns([3, 2, 3, 2])
win = ctl[0].radio("Period", ["1M", "6M", "1Y", "3Y", "5Y", "Max"], index=2, horizontal=True)
kind = ctl[1].radio("Type", ["Candles", "Line"], horizontal=True)
overlay = ctl[2].multiselect("Overlays", ["50 DMA", "200 DMA", "20 DMA", "Volume"], default=["50 DMA", "200 DMA", "Volume"])
log_scale = ctl[3].toggle("Log scale", value=False)

ohlc = live_ohlcv(config.yahoo_ticker(sym))
source_note = "Live OHLCV from Yahoo Finance (cached 1h)"
if ohlc.empty:
    px_store = C.prices()
    if sym in px_store:
        ohlc = px_store[[sym]].dropna().rename(columns={sym: "Close"})
        source_note = "Stored adjusted closes (line only — live OHLCV unavailable)"
        kind = "Line"
cmp_opts = {}
bench = C.benchmarks()
cfgb = config.settings()["benchmarks"]
if cfgb["nifty500"] in bench:
    cmp_opts["Nifty 500"] = bench[cfgb["nifty500"]]
if not prim.empty:
    idx = C.index_series("subsector", prim.iloc[0]["subsector_id"])
    if not idx.empty and "ew" in idx:
        cmp_opts[f"{prim.iloc[0]['subsector_name']} (EW)"] = idx["ew"]
peer_syms = cls[cls["subsector_id"].isin(prim["subsector_id"]) & (cls["nse_symbol"] != sym)]["nse_symbol"].unique().tolist()
compare = st.multiselect("Compare with (rebased to price)", list(cmp_opts) + peer_syms, default=[],
                         format_func=lambda x: x if x in cmp_opts else f"{names.get(x, x)} ({x})")
if ohlc.empty:
    st.warning("No price data for this symbol yet (not refreshed, suspended, or symbol changed). Check the Data Quality page.")
else:
    px_store = C.prices()
    cmp = {}
    for k in compare:
        if k in cmp_opts:
            cmp[k] = cmp_opts[k]
        elif k in px_store:
            cmp[k] = px_store[k]
    months = {"1M": 1, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60, "Max": None}[win]
    start = None if months is None else ohlc.index.max() - pd.DateOffset(months=months)
    dmas = tuple(int(o.split()[0]) for o in overlay if "DMA" in o)
    fig = charts.price_chart(ohlc, sym, kind=kind, dmas=dmas, volume="Volume" in overlay and "Volume" in ohlc,
                             compare=cmp, start=start, log_scale=log_scale)
    st.plotly_chart(fig)
    st.caption(f"{source_note}. Moving averages are computed on the full history before windowing.")

# --------------------------------------------------------------------------- returns
r_cols = ["return_1w", "return_1m", "return_3m", "return_6m", "return_1y", "return_3y", "return_5y"]
rt = {"Stock": [c[x] for x in r_cols]}
from tracker.analytics import series_return  # noqa: E402
if cfgb["nifty500"] in bench:
    s = bench[cfgb["nifty500"]].dropna()
    rt["Nifty 500"] = [series_return(s, len(s) - 1, x.split("_")[1]) for x in r_cols]
if not prim.empty:
    pp = C.perf("subsector").set_index("entity_id")
    if prim.iloc[0]["subsector_id"] in pp.index:
        row = pp.loc[prim.iloc[0]["subsector_id"]]
        rt[f"Sub-sector EW ({prim.iloc[0]['subsector_name']})"] = [row[f"ew_{x.split('_')[1]}"] for x in r_cols]
rdf = pd.DataFrame(rt, index=[C.PERIOD_LABEL[x.split("_")[1]] for x in r_cols]).T * 100
st.dataframe(rdf, column_config={k: C.pct_col(k) for k in rdf.columns})

# --------------------------------------------------------------------------- financials
st.subheader("Financials")
stm = live_statements(config.yahoo_ticker(sym))
if stm:
    fc1, fc2 = st.columns(2)
    if "quarterly" in stm:
        fc1.plotly_chart(charts.financial_bars(stm["quarterly"].tail(8), "Quarterly (₹ crore)"))
    if "annual" in stm:
        fc2.plotly_chart(charts.financial_bars(stm["annual"].tail(5), "Annual (₹ crore)"))
    st.caption("Source: Yahoo Finance statements via yfinance (unofficial; consolidated where available). "
               "Cross-check with exchange filings / Screener before relying on figures.")
else:
    st.caption("Statement charts load live from the data provider when the app is online. Not available right now.")

# --------------------------------------------------------------------------- classification evidence
st.subheader("Classification & evidence")
ev = mine[["sector_name", "subsector_name", "classification_type", "revenue_exposure", "classification_confidence",
           "source_reference", "last_verified"]].copy()
ev["classification_type"] = ev["classification_type"].map(C.TYPE_LABEL)
st.dataframe(ev, hide_index=True, column_config={
    "sector_name": "Sector", "subsector_name": "Sub-sector", "classification_type": "Type", "revenue_exposure": "Exposure",
    "classification_confidence": "Confidence", "source_reference": st.column_config.TextColumn("Source", width="large"),
    "last_verified": "Last verified"})
go_sub = st.selectbox("Open a sub-sector this company belongs to", mine["subsector_id"].tolist(), index=None,
                      format_func=lambda x: mine.set_index("subsector_id").loc[x, "subsector_name"], placeholder="Choose…")
if go_sub:
    C.goto("subsector", subsector_id=go_sub)

# --------------------------------------------------------------------------- peers
st.subheader("Peers (same primary sub-sector)")
if not prim.empty:
    peer_ids = cls[(cls["subsector_id"] == prim.iloc[0]["subsector_id"]) & cls["classification_type"].isin(["primary", "secondary"])]["company_id"]
    pt = comp[comp["company_id"].isin(peer_ids)].merge(fund.drop(columns=["nse_symbol"]), on="company_id", how="left")
    pt = pt[["company_name", "nse_symbol", "market_cap_category", "market_cap_cr", "return_3m", "return_1y", "pe", "roce",
             "revenue_growth"]].sort_values("market_cap_cr", ascending=False)
    pt = C.as_pct_cols(pt, ["return_3m", "return_1y", "roce", "revenue_growth"])
    st.dataframe(pt, hide_index=True, column_config={
        "company_name": "Company", "nse_symbol": "NSE", "market_cap_category": "Cap",
        "market_cap_cr": st.column_config.NumberColumn("Mcap ₹ cr", format="localized"), "return_3m": C.pct_col("3M"),
        "return_1y": C.pct_col("1Y"), "pe": st.column_config.NumberColumn("P/E", format="%.1f"), "roce": C.pct_col("ROCE"),
        "revenue_growth": C.pct_col("Sales growth")})
