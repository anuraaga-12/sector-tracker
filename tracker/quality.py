"""Data-quality and coverage checks (read from the built database)."""
from __future__ import annotations

import re

import pandas as pd

from . import config, db


def _norm(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", str(name).lower())
    n = re.sub(r"\b(ltd|limited|the|india|of|and|&|co|company|corporation|industries)\b", " ", n)
    return re.sub(r"[^a-z0-9]", "", n)


def report(path=None) -> dict[str, pd.DataFrame]:
    q = lambda s: db.read_sql(s, path=path)  # noqa: E731
    cfg = config.settings()["data"]
    comp = q("""SELECT c.company_id, c.nse_symbol, c.company_name, c.listing_status, c.isin, c.bse_code,
                       c.market_cap_cr, c.market_cap_category, c.market_cap_as_of,
                       m.last_price_date, m.last_close
                FROM companies c LEFT JOIN stock_metrics m USING(company_id)""")
    cls = q("""SELECT c.nse_symbol, c.company_name, cc.subsector_id, s.subsector_name, cc.classification_type,
                      cc.classification_confidence, cc.revenue_exposure, cc.last_verified
               FROM company_classification cc JOIN companies c USING(company_id)
               JOIN subsectors s USING(subsector_id)""")
    subs = q("SELECT subsector_id, subsector_name, sector_id FROM subsectors")
    fin = q("SELECT company_id, as_of, source_reference FROM financial_metrics")
    log = q("SELECT * FROM refresh_log")

    out: dict[str, pd.DataFrame] = {}
    latest = pd.to_datetime(comp["last_price_date"]).max()
    out["missing_price"] = comp[comp["last_price_date"].isna()][["nse_symbol", "company_name"]]
    lp = pd.to_datetime(comp["last_price_date"])
    stale = comp[lp.notna() & ((latest - lp).dt.days > cfg["stale_price_days"])]
    out["stale_price"] = stale[["nse_symbol", "company_name", "last_price_date"]]
    out["missing_mcap"] = comp[comp["market_cap_cr"].isna()][["nse_symbol", "company_name"]]
    out["low_confidence"] = cls[cls["classification_confidence"] == "Low"]
    out["unverified_primary"] = cls[(cls["classification_type"] == "primary") & cls["last_verified"].isna()]
    has_primary = set(cls.loc[cls["classification_type"] == "primary", "nse_symbol"])
    out["awaiting_classification"] = comp[~comp["nse_symbol"].isin(has_primary)][["nse_symbol", "company_name"]]
    counts = cls[cls["classification_type"].isin(config.settings()["membership"]["include_types"])].groupby(
        "subsector_id")["nse_symbol"].nunique()
    subs["companies"] = subs["subsector_id"].map(counts).fillna(0).astype(int)
    out["thin_subsectors"] = subs[subs["companies"] < config.settings()["membership"]["min_members_for_ranking"]]
    if not fin.empty:
        age = (pd.Timestamp.today() - pd.to_datetime(fin["as_of"], errors="coerce")).dt.days
        stale_f = fin[age > cfg["stale_fundamentals_days"]]
        out["stale_fundamentals"] = comp[comp["company_id"].isin(stale_f["company_id"])][["nse_symbol", "company_name"]]
    else:
        stale_f = fin
        out["stale_fundamentals"] = pd.DataFrame(columns=["nse_symbol", "company_name"])
    out["missing_fundamentals"] = comp[~comp["company_id"].isin(fin["company_id"])][["nse_symbol", "company_name"]]
    comp["_n"] = comp["company_name"].map(_norm)
    dup_name = comp[comp["_n"].duplicated(keep=False) & (comp["_n"] != "")]
    dup_isin = comp[comp["isin"].notna() & (comp["isin"] != "") & comp["isin"].duplicated(keep=False)]
    out["possible_duplicates"] = pd.concat([dup_name, dup_isin])[["nse_symbol", "company_name", "isin"]].drop_duplicates()
    out["not_mainboard"] = comp[comp["listing_status"] != "Mainboard"][["nse_symbol", "company_name", "listing_status"]]
    out["missing_identifiers"] = comp[comp["isin"].isna() | (comp["isin"] == "")][["nse_symbol", "company_name"]]
    out["refresh_log"] = log
    out["summary"] = pd.DataFrame([
        ("Companies in universe", len(comp)),
        ("Classification mappings", len(cls)),
        ("Companies with price data", int(comp["last_price_date"].notna().sum())),
        ("Missing price data", len(out["missing_price"])),
        ("Stale price data", len(out["stale_price"])),
        ("Missing market cap", len(out["missing_mcap"])),
        ("Missing fundamentals", len(out["missing_fundamentals"])),
        ("Stale fundamentals", len(out["stale_fundamentals"])),
        ("Low-confidence mappings", len(out["low_confidence"])),
        ("Primary mappings not yet verified vs annual report", len(out["unverified_primary"])),
        ("Sub-sectors below ranking minimum", len(out["thin_subsectors"])),
        ("Possible duplicates", len(out["possible_duplicates"])),
        ("Missing ISIN / BSE code", len(out["missing_identifiers"])),
    ], columns=["check", "count"])
    return out
