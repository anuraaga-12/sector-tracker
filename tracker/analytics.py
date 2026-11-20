"""Performance, breadth, momentum and rotation engine.

All functions are pure pandas and are unit-tested in ``tests/``. Conventions:

* Prices are adjusted closes on the benchmark trading calendar (gaps forward-filled ≤5 days).
* Period returns use trading-day offsets: 1W=5, 1M=21, 3M=63, 6M=126, 1Y=252, 3Y=756, 5Y=1260.
  3Y / 5Y are annualised (CAGR).
* Group (sector / sub-sector) returns are reported three ways: equal-weighted index ("ew"),
  cap-weighted index ("cw") and the median constituent return ("med").
* Every point-in-time calculation uses only prices up to that date (no look-ahead in prices).
  Classification membership is the *current* mapping — see README "Known limitations".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}
CAGR_YEARS = {"3y": 3, "5y": 5}
CAP_ORDER = ["Large", "Mid", "Small", "Micro"]


# ----------------------------------------------------------------------------- prices
def align_prices(close: pd.DataFrame, calendar: pd.DatetimeIndex | None = None, ffill_limit: int = 5) -> pd.DataFrame:
    if close.empty:
        return close
    if calendar is None or len(calendar) == 0:
        calendar = close.index[close.notna().sum(axis=1) > 0]
    px = close.reindex(close.index.union(calendar)).sort_index().ffill(limit=ffill_limit)
    return px.reindex(calendar)


def daily_returns(px: pd.DataFrame, max_move: float = 0.40) -> pd.DataFrame:
    r = px.pct_change(fill_method=None)
    return r.where(r.abs() <= max_move)


def returns_at(px: pd.DataFrame, pos: int) -> pd.DataFrame:
    """Per-column period returns ending at integer row ``pos``."""
    end = px.iloc[pos]
    out = {}
    for k, n in PERIODS.items():
        if pos - n < 0:
            out[k] = pd.Series(np.nan, index=px.columns)
            continue
        r = end / px.iloc[pos - n] - 1
        if k in CAGR_YEARS:
            r = (1 + r) ** (1 / CAGR_YEARS[k]) - 1
        out[k] = r
    return pd.DataFrame(out)


def series_return(s: pd.Series, pos: int, period: str) -> float:
    n = PERIODS[period]
    if pos - n < 0 or pd.isna(s.iloc[pos]) or pd.isna(s.iloc[pos - n]) or s.iloc[pos - n] == 0:
        return np.nan
    r = s.iloc[pos] / s.iloc[pos - n] - 1
    if period in CAGR_YEARS:
        r = (1 + r) ** (1 / CAGR_YEARS[period]) - 1
    return float(r)


# ----------------------------------------------------------------------------- indices
def ew_index(daily: pd.DataFrame, syms: list[str]) -> tuple[pd.Series, pd.Series]:
    sub = daily[syms]
    count = sub.notna().sum(axis=1)
    r = sub.mean(axis=1, skipna=True).where(count > 0, 0.0)
    return (1 + r).cumprod() * 100, count


def cw_index(daily: pd.DataFrame, px: pd.DataFrame, syms: list[str], mcap_now: pd.Series) -> pd.Series:
    """Cap-weighted index using weights = shares × previous close.

    Shares are inferred as current market cap / latest price (i.e. assumed constant over the
    window — an approximation noted in the docs)."""
    syms = [s for s in syms if pd.notna(mcap_now.get(s)) and mcap_now.get(s, 0) > 0]
    if not syms:
        return pd.Series(np.nan, index=daily.index)
    last = px[syms].ffill().iloc[-1]
    shares = mcap_now[syms] / last
    w = px[syms].shift(1) * shares
    r = daily[syms]
    valid = r.notna() & w.notna()
    num = (r.where(valid, 0) * w.where(valid, 0)).sum(axis=1)
    den = w.where(valid, 0).sum(axis=1)
    idx_r = (num / den.replace(0, np.nan)).fillna(0.0)
    return (1 + idx_r).cumprod() * 100


# ----------------------------------------------------------------------------- stocks
def stock_metrics(px: pd.DataFrame, pos: int | None = None) -> pd.DataFrame:
    pos = len(px) - 1 if pos is None else pos
    window = px.iloc[: pos + 1]
    rets = returns_at(px, pos)
    rets.columns = [f"return_{c}" for c in rets.columns]
    dma50 = window.rolling(50, min_periods=50).mean().iloc[-1]
    dma200 = window.rolling(200, min_periods=200).mean().iloc[-1]
    last = window.iloc[-1]
    hi = window.iloc[-252:].max()
    lo = window.iloc[-252:].min()
    last_date = window.apply(lambda c: c.last_valid_index())
    df = pd.DataFrame({
        "last_close": last, "last_price_date": last_date, "dma50": dma50, "dma200": dma200,
        "above_50dma": (last > dma50).where(dma50.notna() & last.notna()),
        "above_200dma": (last > dma200).where(dma200.notna() & last.notna()),
        "high_52w": hi, "low_52w": lo, "pct_from_52w_high": last / hi - 1,
    })
    return df.join(rets)


# ----------------------------------------------------------------------------- groups
def _nanpct(x: np.ndarray) -> float:
    """Share of True among non-NaN entries of a float (0/1/NaN) array, in %."""
    x = x[~np.isnan(x)]
    return float(x.mean() * 100) if x.size else np.nan


def _nanmedian(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    return float(np.median(x)) if x.size else np.nan


def group_stats(members: dict[str, np.ndarray], P: np.ndarray, pos: int, R: np.ndarray,
                a50: np.ndarray, a200: np.ndarray, ew_idx: dict, cw_idx: dict,
                bench_ret: dict[str, dict], group_bench: dict[str, str | None], cap_codes: np.ndarray,
                shares: np.ndarray, n500: str, n50: str, n_total: dict[str, int]) -> pd.DataFrame:
    """Vectorised group statistics at row ``pos``.

    ``members`` maps group id -> integer column positions; ``R`` is the (N × periods) matrix of
    stock returns at ``pos`` in PERIODS order; ``cap_codes`` holds 0..3 for Large..Micro (−1 unknown)."""
    pkeys = list(PERIODS)
    b500 = bench_ret.get(n500, {})
    b50 = bench_ret.get(n50, {})
    i3 = pkeys.index("3m")
    rows = []
    for gid, ids in members.items():
        row = {"entity_id": gid, "n_members": n_total[gid], "n_priced": int(np.sum(~np.isnan(P[pos, ids]))) if ids.size else 0}
        r = R[ids] if ids.size else np.empty((0, len(pkeys)))
        for j, p in enumerate(pkeys):
            n = PERIODS[p]
            ok_start = ids.size and pos - n >= 0 and np.any(~np.isnan(P[pos - n, ids]))
            row[f"ew_{p}"] = series_return(ew_idx[gid], pos, p) if ok_start else np.nan
            row[f"cw_{p}"] = series_return(cw_idx[gid], pos, p) if ok_start else np.nan
            row[f"med_{p}"] = _nanmedian(r[:, j]) if r.size else np.nan
            row[f"xs500_{p}"] = row[f"ew_{p}"] - b500.get(p, np.nan)
        for p in ("3m", "6m"):
            row[f"xs50_{p}"] = row[f"ew_{p}"] - b50.get(p, np.nan)
        gb = group_bench.get(gid)
        row["xs_sector_3m"] = row["ew_3m"] - bench_ret[gb]["3m"] if gb in bench_ret else np.nan
        r3 = r[:, i3] if r.size else np.array([])
        row["pct_positive_3m"] = _nanpct(np.where(np.isnan(r3), np.nan, (r3 > 0).astype(float)))
        for p in ("1m", "3m", "6m"):
            br = b500.get(p, np.nan)
            rp = r[:, pkeys.index(p)] if r.size else np.array([])
            row[f"pct_outperf_{p}"] = _nanpct(np.where(np.isnan(rp), np.nan, (rp > br).astype(float))) if not np.isnan(br) else np.nan
        row["pct_above_50dma"] = _nanpct(a50[ids]) if ids.size else np.nan
        row["pct_above_200dma"] = _nanpct(a200[ids]) if ids.size else np.nan
        cc = cap_codes[ids] if ids.size else np.array([])
        for k, c in enumerate(CAP_ORDER):
            row[f"med_3m_{c.lower()}"] = _nanmedian(r3[cc == k]) if r3.size else np.nan
        # concentration: share of the cap-weighted 3M gain contributed by the top-2 stocks
        row["top2_share_3m"] = np.nan
        if pos - 63 >= 0 and ids.size:
            p0, p1, sh = P[pos - 63, ids], P[pos, ids], shares[ids]
            ok = ~np.isnan(p0) & ~np.isnan(p1) & ~np.isnan(sh)
            if ok.sum() >= 3:
                w0 = sh[ok] * p0[ok]
                contrib = (w0 / w0.sum()) * (p1[ok] / p0[ok] - 1)
                pc = np.sort(contrib[contrib > 0])[::-1]
                if pc.size >= 3 and pc.sum() > 0:
                    row["top2_share_3m"] = float(pc[:2].sum() / pc.sum() * 100)
        rows.append(row)
    return pd.DataFrame(rows)


def momentum_components(g: pd.DataFrame, min_members: int) -> pd.DataFrame:
    g = g.copy()
    g["eligible"] = (g["n_priced"] >= min_members).astype(int)
    e = g["eligible"] == 1
    raw = pd.DataFrame(index=g.index)
    raw["relative"] = 0.2 * g["xs500_1m"] + 0.4 * g["xs500_3m"] + 0.4 * g["xs500_6m"]
    raw["absolute"] = g[["ew_3m", "ew_6m"]].mean(axis=1)
    xs = g[[f"xs500_{p}" for p in ("1w", "1m", "3m", "6m", "1y")]]
    raw["consistency"] = (xs > 0).where(xs.notna()).mean(axis=1)
    raw["breadth"] = g["pct_outperf_3m"]
    raw["ma_breadth"] = g[["pct_above_50dma", "pct_above_200dma"]].mean(axis=1)
    for c in raw:
        g[f"c_{c}"] = np.nan
        g.loc[e, f"c_{c}"] = raw.loc[e, c].rank(pct=True) * 100
    return g


def score(g: pd.DataFrame, weights: dict) -> pd.Series:
    tot = sum(weights.values()) or 1
    comps = g[[f"c_{k}" for k in weights]]
    w = pd.Series({f"c_{k}": v / tot for k, v in weights.items()})
    # renormalise per row over available components
    avail = comps.notna().astype(float).mul(w, axis=1).sum(axis=1)
    s = comps.fillna(0).mul(w, axis=1).sum(axis=1) / avail.replace(0, np.nan)
    return s.where(g.get("eligible", 1) == 1)


# ----------------------------------------------------------------------------- engine
def _matrix_indices(daily: pd.DataFrame, px: pd.DataFrame, members: dict[str, list[str]],
                    shares: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Equal- and cap-weighted index levels for many groups at once (T × G matrices)."""
    cols = {c: i for i, c in enumerate(px.columns)}
    gids = list(members)
    M = np.zeros((len(gids), px.shape[1]))
    for g, syms in enumerate(members.values()):
        for s in syms:
            if s in cols:
                M[g, cols[s]] = 1.0
    D = daily.values
    valid = ~np.isnan(D)
    Dz = np.where(valid, D, 0.0)
    cnt = valid.astype(float) @ M.T
    ew_r = np.divide(Dz @ M.T, cnt, out=np.zeros_like(cnt), where=cnt > 0)
    W = np.vstack([np.full(px.shape[1], np.nan), px.values[:-1]]) * shares
    Wv = np.where(valid & ~np.isnan(W) & (W > 0), W, 0.0)
    den = Wv @ M.T
    cw_r = np.divide((Dz * Wv) @ M.T, den, out=np.zeros_like(den), where=den > 0)
    ew = pd.DataFrame(np.cumprod(1 + ew_r, axis=0) * 100, index=px.index, columns=gids)
    cw = pd.DataFrame(np.cumprod(1 + cw_r, axis=0) * 100, index=px.index, columns=gids)
    # undefined before the first constituent traded / before any cap weight existed
    started = pd.DataFrame(np.cumsum(cnt, axis=0) > 0, index=px.index, columns=gids)
    started_cw = pd.DataFrame(np.cumsum(den, axis=0) > 0, index=px.index, columns=gids)
    return ew.where(started), cw.where(started_cw)


def compute_all(close: pd.DataFrame, bench_close: pd.DataFrame, companies: pd.DataFrame,
                classifications: pd.DataFrame, subsectors: pd.DataFrame, sectors: pd.DataFrame,
                cfg: dict) -> dict[str, pd.DataFrame]:
    """Run the full analytics pipeline. Returns DataFrames ready to be written to SQLite."""
    n500, n50 = cfg["benchmarks"]["nifty500"], cfg["benchmarks"]["nifty50"]
    include = set(cfg["membership"]["include_types"])
    min_members = cfg["membership"]["min_members_for_ranking"]
    rot = cfg["rotation"]

    calendar = bench_close[n500].dropna().index if (n500 in bench_close and bench_close[n500].notna().sum() > 250) else None
    px = align_prices(close, calendar)
    bpx = align_prices(bench_close, px.index) if not bench_close.empty else pd.DataFrame(index=px.index)
    daily = daily_returns(px, cfg["data"]["max_daily_move"])

    comp = companies.set_index("nse_symbol")
    mcap_now = comp["market_cap_cr"].astype(float).reindex(px.columns)
    last_px = px.ffill().iloc[-1]
    shares = (mcap_now / last_px).values  # ₹ crore per unit price (scale irrelevant for weights)
    cap_codes = comp["market_cap_category"].reindex(px.columns).map({c: i for i, c in enumerate(CAP_ORDER)}).fillna(-1).values

    cls = classifications[classifications["classification_type"].isin(include)]
    sub_members = cls.groupby("subsector_id")["nse_symbol"].apply(lambda s: sorted(set(s))).to_dict()
    for sid in subsectors["subsector_id"]:
        sub_members.setdefault(sid, [])
    sec_of = subsectors.set_index("subsector_id")["sector_id"]
    sec_members = cls.assign(sector_id=cls["subsector_id"].map(sec_of)).groupby("sector_id")["nse_symbol"].apply(
        lambda s: sorted(set(s))).to_dict()
    for sid in sectors["sector_id"]:
        sec_members.setdefault(sid, [])

    overrides = cfg["benchmarks"].get("sector_overrides") or {}
    sec_bench = {r.sector_id: overrides.get(r.sector_id, r.benchmark) for r in sectors.itertuples()}
    sec_bench = {k: (v if v in bpx and v != n500 else None) for k, v in sec_bench.items()}
    sub_bench = {sid: sec_bench.get(sec_of.get(sid)) for sid in sub_members}

    colpos = {c: i for i, c in enumerate(px.columns)}
    levels = {}
    idx_frames = []
    for level, members in (("subsector", sub_members), ("sector", sec_members)):
        ew, cw = _matrix_indices(daily, px, members, shares)
        ids = {g: np.array([colpos[s] for s in syms if s in colpos], dtype=int) for g, syms in members.items()}
        levels[level] = (members, ids, ew, cw)
        for wname, frame in (("ew", ew), ("cw", cw)):
            long = frame.rename_axis("date").reset_index().melt(id_vars="date", var_name="entity_id", value_name="value").dropna()
            long["date"] = long["date"].dt.strftime("%Y-%m-%d")
            long["value"] = long["value"].round(4)
            idx_frames.append(long.assign(level=level, weighting=wname))
    index_series = pd.concat(idx_frames, ignore_index=True)[["level", "entity_id", "weighting", "date", "value"]]

    last = len(px) - 1
    me = pd.Series(range(len(px)), index=px.index).groupby([px.index.year, px.index.month]).max()
    positions = set(me.values[-rot["history_months"]:].tolist()) | {last, max(last - 21, 0), max(last - 63, 0)}
    positions = sorted(p for p in positions if p >= 0)

    P = px.values
    dma50 = px.rolling(50, min_periods=50).mean().values
    dma200 = px.rolling(200, min_periods=200).mean().values
    weights = cfg["momentum"]["weights"]
    perf = []
    for pos in positions:
        R = returns_at(px, pos).values
        a50 = np.where(np.isnan(dma50[pos]) | np.isnan(P[pos]), np.nan, (P[pos] > dma50[pos]).astype(float))
        a200 = np.where(np.isnan(dma200[pos]) | np.isnan(P[pos]), np.nan, (P[pos] > dma200[pos]).astype(float))
        bret = {c: {p: series_return(bpx[c], pos, p) for p in PERIODS} for c in bpx.columns}
        for level, gb in (("subsector", sub_bench), ("sector", sec_bench)):
            members, ids, ew, cw = levels[level]
            g = group_stats(ids, P, pos, R, a50, a200, {k: ew[k] for k in members}, {k: cw[k] for k in members},
                            bret, gb, cap_codes, shares, n500, n50, {k: len(v) for k, v in members.items()})
            g = momentum_components(g, min_members)
            g["momentum_score"] = score(g, weights)
            g["rank"] = g["momentum_score"].rank(ascending=False, method="min")
            g["level"] = level
            g["calculation_date"] = px.index[pos].strftime("%Y-%m-%d")
            perf.append(g)
    perf = add_flags(pd.concat(perf, ignore_index=True), px.index, last, rot)

    sm = stock_metrics(px, last)
    sm["calculation_date"] = px.index[last].strftime("%Y-%m-%d")
    sm["last_price_date"] = pd.to_datetime(sm["last_price_date"]).dt.strftime("%Y-%m-%d")
    return {"group_performance": perf, "stock_metrics": sm, "index_series": index_series,
            "as_of": px.index[last].strftime("%Y-%m-%d")}


def add_flags(perf: pd.DataFrame, dates: pd.DatetimeIndex, last: int, rot: dict) -> pd.DataFrame:
    d_now = dates[last].strftime("%Y-%m-%d")
    d_1m = dates[max(last - 21, 0)].strftime("%Y-%m-%d")
    d_3m = dates[max(last - 63, 0)].strftime("%Y-%m-%d")
    key = ["level", "entity_id"]
    now = perf[perf["calculation_date"] == d_now].set_index(key)
    m1 = perf[perf["calculation_date"] == d_1m].set_index(key).reindex(now.index)
    m3 = perf[perf["calculation_date"] == d_3m].set_index(key).reindex(now.index)
    flags = pd.Series([[] for _ in range(len(now))], index=now.index)
    ds = now["momentum_score"] - m1["momentum_score"]
    db = now["pct_above_50dma"] - m1["pct_above_50dma"]
    small = now[["med_3m_small", "med_3m_micro"]].mean(axis=1)
    big = now[["med_3m_large", "med_3m_mid"]].mean(axis=1)
    rules = {
        "Improving momentum": ds >= rot["improving_score_delta"],
        "Weakening momentum": ds <= -rot["improving_score_delta"],
        "Improving breadth": db >= rot["breadth_improve_pp"],
        "Narrow leadership": ((now["cw_3m"] - now["med_3m"]) * 100 >= rot["narrow_gap_pp"]) | (now["top2_share_3m"] >= 70),
        "Small caps leading": (small - big) * 100 >= rot["small_vs_large_pp"],
        "Early strength": (m3["momentum_score"] < 50) & (now["momentum_score"] >= 60) & (now["xs500_1m"] > 0),
    }
    for name, mask in rules.items():
        for i in mask[mask.fillna(False)].index:
            flags[i].append(name)
    now_flags = flags.map(lambda x: "|".join(x)).to_dict()
    perf = perf.copy()
    perf["flags"] = [now_flags.get((l, e), "") if d == d_now else ""
                     for l, e, d in zip(perf["level"], perf["entity_id"], perf["calculation_date"])]
    return perf
