"""Data Quality & Coverage — see the gaps instead of blindly trusting the universe."""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from dashboard import common as C
from tracker import config, quality, store

C.setup("Data Quality", "🧪")
st.title("🧪 Data Quality & Coverage")

rep = quality.report()
fresh = C.freshness()

st.subheader("Freshness")
rows = []
for key, lab in (("prices", "Last stock price update"), ("market_cap", "Last market-cap (shares) update"),
                 ("fundamentals", "Last fundamental data update"), ("classification_seed", "Last classification change"),
                 ("amfi", "AMFI categorisation import"), ("database_build", "Last database build")):
    r = fresh.get(key, {})
    rows.append({"Item": lab, "Timestamp (UTC)": str(r.get("last_refresh", "never"))[:19].replace("T", " "),
                 "Status": r.get("status", "—"), "Detail": r.get("detail", "")})
st.dataframe(pd.DataFrame(rows), hide_index=True)
st.caption(f"Latest market date in the dataset: **{C.as_of() or 'n/a'}**. The dashboard is end-of-day; nothing is live. "
           "Classification mappings carry 'last verified' = blank until checked against an annual report.")

st.subheader("Summary")
st.dataframe(rep["summary"], hide_index=True)

checks = [
    ("missing_price", "Companies with no price data", "Symbol may be wrong / renamed / suspended, or the price job has not run."),
    ("stale_price", "Stale price data", "Last price older than the stale threshold relative to the latest market date."),
    ("missing_mcap", "Missing market cap", "Run the weekly job (shares outstanding) or check the symbol."),
    ("awaiting_classification", "Companies awaiting classification", "No primary sub-sector assigned."),
    ("low_confidence", "Low-confidence mappings", "Disclosures insufficient — verify before relying on these."),
    ("unverified_primary", "Primary mappings not yet verified against annual reports", "Set last_verified once checked."),
    ("thin_subsectors", "Thin sub-sectors (below ranking minimum)", "Coverage gaps — add companies or merge sub-sectors."),
    ("missing_fundamentals", "Missing fundamentals", "Provider returned nothing; consider a manual override file."),
    ("stale_fundamentals", "Stale fundamentals", "Older than the configured threshold."),
    ("possible_duplicates", "Possible duplicate securities", "Same normalised name or ISIN."),
    ("not_mainboard", "Not mainboard (SME / suspended / delisted)", "Kept for history — excluded from nothing automatically."),
    ("missing_identifiers", "Missing ISIN / BSE code", "Add via data/manual/company_master_override.csv."),
]
for key, title, help_ in checks:
    df = rep.get(key, pd.DataFrame())
    with st.expander(f"{title} · {len(df)}"):
        st.caption(help_)
        st.dataframe(df, hide_index=True)

hist = C.q("SELECT * FROM classification_history ORDER BY changed_on DESC")
with st.expander(f"Classification change history · {len(hist)}"):
    st.caption("Every add / remove / type change to a mapping is recorded so history never silently disappears.")
    st.dataframe(hist, hide_index=True)

# --------------------------------------------------------------------------- export / import
st.subheader("Export / import")
cls = C.classifications()
comp = C.companies()
e1, e2, e3 = st.columns(3)
e1.download_button("⬇️ Company universe (CSV)", comp.to_csv(index=False).encode(), "company_universe.csv", "text/csv")
e2.download_button("⬇️ Classifications (CSV)", cls.to_csv(index=False).encode(), "classifications.csv", "text/csv")
gp = C.perf("subsector")
e3.download_button("⬇️ Sub-sector performance (CSV)", gp.to_csv(index=False).encode(), "subsector_performance.csv", "text/csv")
st.caption("To add or re-classify companies permanently, edit `data/seed/universe/*.csv` (one row per company) and "
           "commit — see README › Adding companies. Uploads below are applied to this running instance only.")
up = st.file_uploader("Manual price import (long CSV: symbol,date,close)", type="csv")
if up is not None and st.button("Import prices"):
    tmp = config.DATA / "_upload_prices.csv"
    tmp.write_bytes(up.getvalue())
    from tracker import refresh
    refresh.import_prices(str(tmp), log=st.write)
    st.cache_data.clear()
    st.success("Imported. Rebuilding on next page load.")

# --------------------------------------------------------------------------- refresh
st.subheader("Refresh data on this instance")
secret = None
try:
    secret = st.secrets.get("ADMIN_PASSWORD")
except Exception:
    secret = None
st.caption("Recommended: let the scheduled GitHub Action refresh and commit data daily. This button refreshes only "
           "this running server (ephemeral on free hosts) and is rate-limited to protect the data provider.")
pw = st.text_input("Admin password", type="password") if secret else ""
log = store.read_log().get("prices", {})
last = pd.to_datetime(log.get("last_refresh")) if log.get("last_refresh") else None
cool = last is not None and (pd.Timestamp.now(tz="UTC") - last).total_seconds() < 6 * 3600
if config.DATA_MODE == "demo":
    st.info("Refresh disabled in demo mode.")
elif st.button("🔄 Refresh prices now", disabled=cool and not secret):
    if secret and pw != secret:
        st.error("Wrong password.")
    else:
        from tracker import build, refresh
        with st.status("Refreshing prices (several minutes for ~700 stocks) …", expanded=True) as stt:
            refresh.refresh_prices(log=stt.write)
            if not config.QUOTES_FILE.exists():
                refresh.refresh_quotes(log=stt.write)
            build.build(log=stt.write)
            stt.update(label="Done", state="complete")
        st.cache_data.clear()
        st.cache_resource.clear()
        time.sleep(1)
        st.rerun()
if cool and not secret:
    st.caption("Last refresh < 6 hours ago — button disabled.")
