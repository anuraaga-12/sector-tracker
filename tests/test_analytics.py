import numpy as np
import pandas as pd
import pytest

from tracker import analytics as A
from tracker import store


def _px(days=400, **cols):
    idx = pd.bdate_range("2024-01-01", periods=days)
    return pd.DataFrame({k: v for k, v in cols.items()}, index=idx)


def test_period_returns_exact():
    n = 1300
    p = 100 * (1.001 ** np.arange(n))
    px = _px(n, A=p)
    r = A.returns_at(px, n - 1).loc["A"]
    assert r["1w"] == pytest.approx(1.001 ** 5 - 1)
    assert r["3m"] == pytest.approx(1.001 ** 63 - 1)
    assert r["5y"] == pytest.approx((1.001 ** 1260) ** (1 / 5) - 1)  # CAGR


def test_returns_nan_before_listing():
    p = np.r_[np.full(300, np.nan), np.linspace(10, 20, 100)]
    px = _px(400, A=p)
    r = A.returns_at(px, 399).loc["A"]
    assert np.isnan(r["6m"])          # stock did not exist 126 days ago
    assert not np.isnan(r["1m"])


def test_equal_and_cap_weighted_index():
    px = _px(3, A=[100, 110, 110], B=[100, 100, 90])
    d = A.daily_returns(px)
    ew, cnt = A.ew_index(d, ["A", "B"])
    assert ew.iloc[1] == pytest.approx(105.0)                  # (+10% + 0%) / 2
    assert ew.iloc[2] == pytest.approx(105.0 * (1 + (0 - 0.10) / 2))
    cw = A.cw_index(d, px, ["A", "B"], pd.Series({"A": 300.0, "B": 100.0}))
    # day 1 weights proportional to shares × prev close: A=3×100, B=1×100 (shares from mcap / last price)
    shares_a, shares_b = 300 / 110, 100 / 90
    w_a, w_b = shares_a * 100, shares_b * 100
    assert cw.iloc[1] == pytest.approx(100 * (1 + (w_a * 0.10) / (w_a + w_b)))


def test_bad_ticks_are_excluded():
    px = _px(3, A=[100, 300, 300])   # +200% in a day -> treated as data error
    d = A.daily_returns(px, max_move=0.4)
    assert np.isnan(d["A"].iloc[1])


def test_merge_prices_detects_adjustment_change():
    old = _px(10, A=np.arange(10, 20, dtype=float), B=np.arange(10, 20, dtype=float))
    new = old.iloc[-5:].copy()
    new["A"] = new["A"] / 2          # split re-based history for A
    merged, needs_full = store.merge_prices(old, new)
    assert needs_full == ["A"]
    assert merged.shape == old.shape


def _toy_universe(days=700, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=days)
    bench = pd.DataFrame({"^CRSLDX": 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, days))),
                          "^NSEI": 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, days)))}, index=idx)
    trend = {"S1": 0.003, "S2": 0.0, "S3": -0.002}
    cols, cls = {}, []
    for sub, mu in trend.items():
        for i in range(4):
            sym = f"{sub}_{i}"
            cols[sym] = 50 * np.exp(np.cumsum(rng.normal(mu, 0.01, days)))
            cls.append({"nse_symbol": sym, "subsector_id": sub, "classification_type": "primary" if i < 3 else "indirect"})
    close = pd.DataFrame(cols, index=idx)
    comps = pd.DataFrame({"nse_symbol": list(cols), "market_cap_cr": np.linspace(1000, 200000, len(cols)),
                          "market_cap_category": ["Small", "Mid", "Large", "Micro"] * 3})
    subs = pd.DataFrame({"subsector_id": list(trend), "sector_id": ["X", "X", "Y"]})
    secs = pd.DataFrame({"sector_id": ["X", "Y"], "benchmark": [None, None]})
    cfg = {"benchmarks": {"nifty500": "^CRSLDX", "nifty50": "^NSEI", "sector_overrides": {}},
           "data": {"max_daily_move": 0.4}, "membership": {"include_types": ["primary", "secondary"], "min_members_for_ranking": 3},
           "rotation": {"history_months": 6, "improving_score_delta": 10, "breadth_improve_pp": 15, "narrow_gap_pp": 10,
                        "small_vs_large_pp": 5},
           "momentum": {"weights": {"relative": .3, "absolute": .2, "consistency": .15, "breadth": .2, "ma_breadth": .15}}}
    return close, bench, comps, pd.DataFrame(cls), subs, secs, cfg


def test_compute_all_ranks_strong_trend_first_and_ignores_indirect():
    close, bench, comps, cls, subs, secs, cfg = _toy_universe()
    res = A.compute_all(close, bench, comps, cls, subs, secs, cfg)
    gp = res["group_performance"]
    latest = gp[(gp["calculation_date"] == res["as_of"]) & (gp["level"] == "subsector")].set_index("entity_id")
    assert latest.loc["S1", "rank"] == 1 and latest.loc["S3", "rank"] == 3
    assert (latest["n_members"] == 3).all()                   # indirect member excluded
    # median of constituent 3M returns matches a direct computation
    r3 = close.iloc[-1] / close.iloc[-1 - 63] - 1
    assert latest.loc["S2", "med_3m"] == pytest.approx(r3[["S2_0", "S2_1", "S2_2"]].median())
    # breadth % beating N500 is consistent with constituent returns
    b3 = bench["^CRSLDX"].iloc[-1] / bench["^CRSLDX"].iloc[-1 - 63] - 1
    exp = (r3[["S1_0", "S1_1", "S1_2"]] > b3).mean() * 100
    assert latest.loc["S1", "pct_outperf_3m"] == pytest.approx(exp)
    assert 0 <= latest["momentum_score"].min() and latest["momentum_score"].max() <= 100


def test_no_look_ahead_in_history():
    close, bench, comps, cls, subs, secs, cfg = _toy_universe()
    a = A.compute_all(close, bench, comps, cls, subs, secs, cfg)["group_performance"]
    cut = close.index[-60]
    close2 = close.copy()
    close2.loc[close2.index > cut] *= 3          # change the future
    bench2 = bench.copy()
    bench2.loc[bench2.index > cut] *= 0.5
    b = A.compute_all(close2, bench2, comps, cls, subs, secs, cfg)["group_performance"]
    d = max(x for x in a["calculation_date"].unique() if pd.Timestamp(x) <= cut)
    cols = ["ew_3m", "med_3m", "pct_outperf_3m", "pct_above_50dma"]
    pa = a[a["calculation_date"] == d].set_index(["level", "entity_id"])[cols]
    pb = b[b["calculation_date"] == d].set_index(["level", "entity_id"])[cols]
    pd.testing.assert_frame_equal(pa.sort_index(), pb.sort_index())


def test_score_reweights_live():
    g = pd.DataFrame({"c_relative": [100, 0], "c_absolute": [0, 100], "c_consistency": [50, 50],
                      "c_breadth": [50, 50], "c_ma_breadth": [50, 50], "eligible": [1, 1]})
    only_rel = A.score(g, {"relative": 1, "absolute": 0, "consistency": 0, "breadth": 0, "ma_breadth": 0})
    assert list(only_rel) == [100, 0]
