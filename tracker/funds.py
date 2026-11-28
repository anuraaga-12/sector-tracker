"""Mutual-fund refresh: NAV history (daily) and portfolio holdings (as each month's disclosure appears).

    python -m tracker.refresh funds

Files written (all under data/market/):
* mf_nav.csv.gz        dates × AMFI code, NAV (Direct-Growth plans + one index fund per category as benchmark)
* mf_holdings.csv.gz   as_of, amfi, holding_type, instrument, isin, industry, quantity, value_cr, pct_nav
* mf_funds.csv         amfi, name, category, role (fund / benchmark), scheme_name, fund_house, portfolio_id
* isin_reference.csv.gz isin, symbol, company, size (Nifty 100 = Large, Midcap 150 = Mid, other = Small)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import config, store


def fund_list() -> pd.DataFrame:
    """Tracked funds from settings.yaml: amfi, name, category, role."""
    cfg = config.settings().get("funds") or {}
    rows = []
    for cat, c in (cfg.get("categories") or {}).items():
        b = c.get("benchmark") or {}
        if b.get("code"):
            rows.append({"amfi": str(b["code"]), "name": b.get("name", str(b["code"])), "category": cat, "role": "benchmark"})
        for code, name in (c.get("funds") or {}).items():
            rows.append({"amfi": str(code), "name": str(name), "category": cat, "role": "fund"})
    return pd.DataFrame(rows, columns=["amfi", "name", "category", "role"])


def _read_funds_meta() -> pd.DataFrame:
    if not config.MF_FUNDS_FILE.exists():
        return pd.DataFrame(columns=["amfi", "portfolio_id"])
    return pd.read_csv(config.MF_FUNDS_FILE, dtype=str, keep_default_na=False)


def _log_age_days(component: str) -> float:
    row = store.read_log().get(component)
    if not row:
        return float("inf")
    ts = pd.Timestamp(row["last_refresh"])
    return (pd.Timestamp.now(tz=ts.tz) - ts).total_seconds() / 86400


def refresh_funds(log=print) -> None:
    from .providers import mf
    cfg = config.settings().get("funds") or {}
    if not cfg.get("enabled", True):
        return
    funds = fund_list()
    if funds.empty:
        return
    tracked = set(funds["amfi"])
    is_fund = funds["role"] == "fund"
    notes, status = [], "ok"

    # ------------------------------------------------------------------ NAV
    log(f"Mutual funds: downloading NAV history for {len(funds)} schemes …")
    old = store.read_wide(config.MF_NAV_FILE)
    navs, meta = {}, {}
    for code in funds["amfi"]:
        m, s = mf.nav_history(code)
        if not s.empty:
            navs[code], meta[code] = s, m
    if navs:
        new = pd.DataFrame(navs)
        nav = new.combine_first(old) if not old.empty else new   # fresh download wins on overlap
        cutoff = pd.Timestamp(date.today() - timedelta(days=int(365.25 * cfg.get("nav_years", 6)) + 10))
        nav = nav[nav.index >= cutoff]
        nav = nav[[c for c in nav.columns if c in tracked]]
        store.write_wide(nav, config.MF_NAV_FILE)
        notes.append(f"NAV {len(navs)}/{len(funds)} (latest {nav.index.max().date()})")
    else:
        status = "error"
        notes.append("NAV source unavailable")
    if len(navs) < len(funds):
        miss = sorted(tracked - set(navs))
        notes.append(f"no NAV for {', '.join(miss)}")
        status = "warn" if navs else "error"

    # ------------------------------------------------------------------ fund metadata + holdings
    prev = _read_funds_meta()
    prev = prev.set_index("amfi") if not prev.empty else pd.DataFrame()
    fm = funds.copy()
    for c in ("scheme_name", "fund_house"):
        fm[c] = fm["amfi"].map(lambda x: (meta.get(x) or {}).get(c) or "")
    fm["portfolio_id"] = ""
    for c in ("scheme_name", "fund_house", "portfolio_id"):   # keep last known values if a source is down
        if c in prev:
            fm[c] = fm[c].where(fm[c] != "", fm["amfi"].map(prev[c]).fillna(""))

    months = mf.monthly_filings()[: int(cfg.get("months", 6))]
    hold = store.read_table(config.MF_HOLDINGS_FILE)
    if not hold.empty:
        hold["amfi"] = hold["amfi"].astype(str)
    have = set(zip(hold["as_of"], hold["amfi"])) if not hold.empty else set()
    fund_codes = fm.loc[is_fund, "amfi"].tolist()
    wanted = [(m, c) for m in months for c in fund_codes if (m, c) not in have]
    fetched = []
    if wanted:
        lookup = mf.catalogue()
        if not lookup:
            notes.append("holdings catalogue unavailable")
        for c in fund_codes:
            pid = str((lookup.get(c) or {}).get("portfolio_id") or "")
            if pid:
                fm.loc[fm["amfi"] == c, "portfolio_id"] = pid
        for m, c in wanted:
            entry = lookup.get(c) or {}
            avail = entry.get("available_as_of")
            if avail is not None and m not in avail:
                continue                      # not filed (yet) — don't request
            pid = fm.loc[fm["amfi"] == c, "portfolio_id"].iloc[0]
            if not pid:
                continue
            df = mf.portfolio(m, pid)
            if df.empty:
                continue
            df.insert(0, "amfi", c)
            df.insert(0, "as_of", m)
            fetched.append(df)
    if fetched:
        hold = pd.concat([hold] + fetched, ignore_index=True) if not hold.empty else pd.concat(fetched, ignore_index=True)
    if not hold.empty:
        hold = hold[hold["amfi"].isin(set(fund_codes)) & hold["as_of"].isin(months or hold["as_of"].unique())]
        hold = hold.sort_values(["as_of", "amfi", "pct_nav"], ascending=[True, True, False])
        store.write_table(hold, config.MF_HOLDINGS_FILE)
        latest = hold["as_of"].max()
        n_latest = hold.loc[hold["as_of"] == latest, "amfi"].nunique()
        notes.append(f"holdings as of {latest}: {n_latest}/{len(fund_codes)} funds")
        if fetched:
            notes.append(f"{len(fetched)} new disclosures")
    elif months:
        status = "warn" if status == "ok" else status
        notes.append("no holdings yet")
    else:
        status = "warn" if status == "ok" else status
        notes.append("holdings archive unavailable")
    store.write_table(fm, config.MF_FUNDS_FILE)

    # ------------------------------------------------------------------ ISIN reference (weekly, or with new holdings)
    if fetched or not config.ISIN_FILE.exists() or _log_age_days("isin_reference") > 6:
        ref = mf.isin_reference()
        if not ref.empty:
            store.write_table(ref, config.ISIN_FILE)
            store.write_log("isin_reference", "ok", f"{len(ref)} NSE ISINs")
        else:
            notes.append("NSE ISIN list unavailable (kept previous)")

    store.write_log("funds", status, "; ".join(notes))
    log("Mutual funds: " + "; ".join(notes))


# ============================================================================ analytics (used by the dashboard)
NAV_PERIODS = {"1m": (pd.DateOffset(months=1), None), "3m": (pd.DateOffset(months=3), None),
               "6m": (pd.DateOffset(months=6), None), "1y": (pd.DateOffset(years=1), None),
               "3y": (pd.DateOffset(years=3), 3), "5y": (pd.DateOffset(years=5), 5)}
CASH_TYPES = {"cash", "money_market", "fund_unit", "debt"}


def nav_returns(nav: pd.DataFrame) -> pd.DataFrame:
    """Point-to-point NAV returns per scheme (columns of ``nav``) on calendar periods; 3Y / 5Y annualised.
    A period is blank when the scheme's history doesn't reach back that far."""
    rows = {}
    for code in nav.columns:
        s = nav[code].dropna()
        if s.empty:
            continue
        end_d, end = s.index[-1], s.iloc[-1]
        r = {"nav": end, "nav_date": end_d}
        for k, (off, yrs) in NAV_PERIODS.items():
            start_d = end_d - off
            if s.index[0] > start_d + pd.Timedelta(days=4):
                r[k] = float("nan")
                continue
            v = s.asof(start_d)
            ret = end / v - 1
            r[k] = (1 + ret) ** (1 / yrs) - 1 if yrs else ret
        rows[code] = r
    return pd.DataFrame.from_dict(rows, orient="index")


def classify_rows(h: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Attach symbol / size and an asset bucket to holdings rows.
    bucket: Indian stock · Foreign stock · REIT / InvIT · Cash & debt · Derivatives · Other."""
    h = h.copy()
    if not ref.empty:
        r = ref.drop_duplicates("isin").set_index("isin")
        h["symbol"] = h["isin"].map(r["symbol"])
        h["size"] = h["isin"].map(r["size"])
    else:
        h["symbol"], h["size"] = pd.NA, pd.NA
    isin = h["isin"].fillna("").astype(str)
    name = h["instrument"].fillna("").astype(str)
    stockish = h["holding_type"].isin(["equity", "commodity"])
    reit = stockish & name.str.contains(r"\bREIT\b|Real Estate Trust|Realty Trust|InvIT|Infrastructure Trust|Office Parks|Select Trust",
                                       case=False, regex=True)
    bucket = pd.Series("Other", index=h.index)
    bucket[stockish & isin.str.startswith("IN")] = "Indian stock"
    bucket[stockish & isin.ne("") & ~isin.str.startswith("IN")] = "Foreign stock"
    bucket[reit] = "REIT / InvIT"
    bucket[h["holding_type"].isin(CASH_TYPES)] = "Cash & debt"
    bucket[h["holding_type"].eq("derivative")] = "Derivatives"
    h["bucket"] = bucket
    h.loc[h["bucket"] == "Indian stock", "size"] = h.loc[h["bucket"] == "Indian stock", "size"].fillna("Unlisted / other")
    return h


def stock_positions(hold: pd.DataFrame, amfi: str, ref: pd.DataFrame) -> tuple[pd.DataFrame, str | None, str | None]:
    """One fund's stock holdings in its latest disclosure vs the one before.
    Returns (frame, latest as_of, previous as_of). Status: New / Added / Trimmed / Held / Exited.
    Quantity changes can also come from splits and bonus issues."""
    h = classify_rows(hold[hold["amfi"] == amfi], ref)
    h = h[h["bucket"].isin(["Indian stock", "Foreign stock", "REIT / InvIT"])]
    months = sorted(h["as_of"].unique())
    if not months:
        return pd.DataFrame(), None, None
    cur_m, prev_m = months[-1], (months[-2] if len(months) > 1 else None)
    # Company-level key: an Indian ISIN's first 9 characters (IN + issuer + security type) stay the same when a
    # face-value split changes the last digits; otherwise fall back to the instrument name.
    isin = h["isin"].fillna("").astype(str)
    key = isin.str[:9].where(isin.str.startswith("IN") & (isin.str.len() == 12), isin)
    h = h.assign(key=key.where(key != "", h["instrument"].str.lower().str.strip()))
    agg = dict(instrument=("instrument", "first"), symbol=("symbol", "first"), industry=("industry", "first"),
               size=("size", "first"), bucket=("bucket", "first"), quantity=("quantity", "sum"),
               value_cr=("value_cr", "sum"), pct_nav=("pct_nav", "sum"))
    cur = h[h["as_of"] == cur_m].groupby("key").agg(**agg)
    if prev_m is None:
        for c in ("prev_pct", "prev_qty", "prev_value", "qty_change"):
            cur[c] = float("nan")
        cur["status"] = "—"
        return cur.reset_index().sort_values("pct_nav", ascending=False), cur_m, None
    prev = h[h["as_of"] == prev_m].groupby("key").agg(**agg)
    out = cur.join(prev[["pct_nav", "quantity", "value_cr"]].rename(
        columns={"pct_nav": "prev_pct", "quantity": "prev_qty", "value_cr": "prev_value"}), how="outer")
    gone = out["pct_nav"].isna()
    out.loc[gone, ["instrument", "symbol", "industry", "size", "bucket"]] = prev.loc[out.index[gone],
                                                                                   ["instrument", "symbol", "industry", "size", "bucket"]].values
    out.loc[gone, ["pct_nav", "quantity", "value_cr"]] = 0.0
    ratio = out["quantity"] / out["prev_qty"]
    # Splits / bonus issues multiply the share count while the price per share falls by the same factor.
    px_ratio = (out["prev_value"] / out["prev_qty"]) / (out["value_cr"] / out["quantity"])
    for k in (1.5, 2.5, *range(2, 21)):
        hit = ((ratio / k - 1).abs() < 0.03) & ((px_ratio / k - 1).abs() < 0.25)
        ratio = ratio.where(~hit, ratio / k)
    chg = ratio - 1
    out["status"] = "Held"
    out.loc[chg > 0.02, "status"] = "Added"
    out.loc[chg < -0.02, "status"] = "Trimmed"
    out.loc[out["prev_qty"].isna(), "status"] = "New"
    out.loc[gone, "status"] = "Exited"
    out["qty_change"] = chg.where(out["prev_qty"].notna() & ~gone)
    return out.reset_index().sort_values("pct_nav", ascending=False), cur_m, prev_m


def asset_mix(hold: pd.DataFrame, amfi: str, as_of: str, ref: pd.DataFrame) -> pd.Series:
    """% of NAV by bucket, with Indian stocks split by size (Large / Mid / Small / Unlisted)."""
    h = classify_rows(hold[(hold["amfi"] == amfi) & (hold["as_of"] == as_of)], ref)
    lab = h["bucket"].where(h["bucket"] != "Indian stock", h["size"].fillna("Unlisted / other") + " cap")
    lab = lab.replace({"Unlisted / other cap": "Other Indian equity"})
    return h.groupby(lab)["pct_nav"].sum()


def category_flows(hold: pd.DataFrame, codes: list[str], ref: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Across a set of funds (latest month vs previous): per stock, how many funds hold it, the total
    value held, the average weight, and how many funds bought in / added / trimmed / exited.
    ``net_value_cr`` estimates money put in (+) or taken out (−) at the latest month-end price."""
    frames, latest = [], None
    for c in codes:
        f, cur_m, _ = stock_positions(hold, c, ref)
        if f.empty:
            continue
        latest = max(latest or cur_m, cur_m)
        f["amfi"] = c
        # money in (+) / out (−): quantity change × latest month-end price; an exit uses the previous value
        # held / added / trimmed: value × chg / (1 + chg), with chg already adjusted for splits and bonus issues
        chg = f["qty_change"]
        f["flow_cr"] = f["value_cr"] * chg / (1 + chg)
        f.loc[f["status"] == "New", "flow_cr"] = f.loc[f["status"] == "New", "value_cr"]
        f.loc[f["status"] == "Exited", "flow_cr"] = -f.loc[f["status"] == "Exited", "prev_value"]
        frames.append(f)
    if not frames:
        return pd.DataFrame(), None
    a = pd.concat(frames, ignore_index=True)
    held = a[a["status"] != "Exited"]
    g = held.groupby("key").agg(instrument=("instrument", "first"), symbol=("symbol", "first"), industry=("industry", "first"),
                                size=("size", "first"), funds=("amfi", "nunique"), value_cr=("value_cr", "sum"),
                                avg_pct=("pct_nav", "mean"), max_pct=("pct_nav", "max"))
    cnt = a.pivot_table(index="key", columns="status", values="amfi", aggfunc="nunique", fill_value=0)
    for s in ("New", "Added", "Trimmed", "Exited"):
        g[s.lower()] = cnt[s].reindex(g.index).fillna(0).astype(int) if s in cnt else 0
    flows = a.groupby("key")["flow_cr"].sum(min_count=1)
    ex = a[a["status"] == "Exited"].groupby("key").agg(instrument=("instrument", "first"), symbol=("symbol", "first"),
                                                       industry=("industry", "first"), size=("size", "first"),
                                                       exited=("amfi", "nunique"))
    ex = ex[~ex.index.isin(g.index)]
    if not ex.empty:
        ex["funds"] = 0
        g = pd.concat([g, ex])
    for c in ("new", "added", "trimmed", "exited", "funds"):
        g[c] = g[c].fillna(0).astype(int)
    g["net_value_cr"] = flows.reindex(g.index)
    return g.reset_index(), latest
