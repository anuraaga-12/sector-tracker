"""Mutual-fund refresh + analytics, with the network sources replaced by fakes."""
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tracker import config, funds as F, store
from tracker.providers import mf

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = {"funds": {"enabled": True, "months": 6, "nav_years": 6, "categories": {
    "Small cap": {"benchmark": {"code": 900, "name": "Smallcap index (index fund)"},
                  "funds": {101: "Fund A", 102: "Fund B"}}}}}


def _portfolio(m: str, pid: str) -> pd.DataFrame:
    """Two months: in October fund A adds to X, exits Y, buys Z; stock S has a 1:10 split (new ISIN serial)."""
    oct_ = m == "2026-10-31"
    rows = [("equity", "Stock X", "INE000X01011", "Banks", 1200 if oct_ and pid == "p101" else 1000, 10.0),
            ("equity", "Stock S", "INE000S01029" if oct_ else "INE000S01011", "Power", 10000 if oct_ else 1000, 5.0),
            ("cash", "Cash", None, None, None, 3.0)]
    if not oct_:
        rows.append(("equity", "Stock Y", "INE000Y01011", "Retailing", 500, 2.0))
    elif pid == "p101":
        rows.append(("equity", "Stock Z", "INE000Z01011", "Retailing", 300, 1.5))
    df = pd.DataFrame(rows, columns=["holding_type", "instrument", "isin", "industry", "quantity", "pct_nav"])
    df["section"] = ""
    df["value_cr"] = df["pct_nav"] * 10.0
    return df


@pytest.fixture()
def fake_sources(monkeypatch, tmp_path):
    for name, fn in (("MF_NAV_FILE", "mf_nav.csv.gz"), ("MF_HOLDINGS_FILE", "mf_holdings.csv.gz"),
                     ("MF_FUNDS_FILE", "mf_funds.csv"), ("ISIN_FILE", "isin_reference.csv.gz"),
                     ("REFRESH_LOG", "refresh_log.json")):
        monkeypatch.setattr(config, name, tmp_path / fn)
    monkeypatch.setattr(config, "settings", lambda: SETTINGS)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=800)
    calls = {"portfolio": 0}

    def nav_history(code):
        g = {"101": 0.0006, "102": 0.0002, "900": 0.0004}[str(code)]
        return {"scheme_name": f"Scheme {code}", "fund_house": "AMC"}, pd.Series(100 * np.exp(g * np.arange(len(idx))), index=idx)

    def portfolio(m, pid):
        calls["portfolio"] += 1
        return _portfolio(m, pid)

    monkeypatch.setattr(mf, "nav_history", nav_history)
    monkeypatch.setattr(mf, "monthly_filings", lambda: ["2026-10-31", "2026-09-30"])
    monkeypatch.setattr(mf, "catalogue", lambda: {"101": {"portfolio_id": "p101", "available_as_of": ["2026-10-31", "2026-09-30"]},
                                                  "102": {"portfolio_id": "p102", "available_as_of": ["2026-09-30"]}})
    monkeypatch.setattr(mf, "portfolio", portfolio)
    monkeypatch.setattr(mf, "isin_reference", lambda: pd.DataFrame({
        "isin": ["INE000X01011", "INE000S01029", "INE000Y01011", "INE000Z01011"], "symbol": ["XX", "SS", "YY", "ZZ"],
        "company": ["X", "S", "Y", "Z"], "size": ["Large", "Mid", "Small", "Small"]}))
    return calls


def test_refresh_writes_files_and_is_incremental(fake_sources):
    F.refresh_funds(log=lambda *a: None)
    nav = store.read_wide(config.MF_NAV_FILE)
    assert set(nav.columns) == {"101", "102", "900"}
    hold = store.read_table(config.MF_HOLDINGS_FILE)
    # fund B hasn't filed October yet (not in its available_as_of), so it is not requested
    assert sorted(set(zip(hold["as_of"], hold["amfi"].astype(str)))) == [
        ("2026-09-30", "101"), ("2026-09-30", "102"), ("2026-10-31", "101")]
    assert fake_sources["portfolio"] == 3
    meta = pd.read_csv(config.MF_FUNDS_FILE, dtype=str)
    assert meta.set_index("amfi").loc["101", "portfolio_id"] == "p101"
    assert store.read_log()["funds"]["status"] == "ok"
    F.refresh_funds(log=lambda *a: None)          # nothing new to fetch on the next run
    assert fake_sources["portfolio"] == 3


def test_positions_status_and_split_adjustment(fake_sources):
    F.refresh_funds(log=lambda *a: None)
    hold = store.read_table(config.MF_HOLDINGS_FILE)
    hold["amfi"] = hold["amfi"].astype(str)
    ref = store.read_table(config.ISIN_FILE)
    pos, cur, prev = F.stock_positions(hold, "101", ref)
    st = pos.set_index("instrument")["status"].to_dict()
    assert (cur, prev) == ("2026-10-31", "2026-09-30")
    assert st == {"Stock X": "Added", "Stock S": "Held", "Stock Z": "New", "Stock Y": "Exited"}
    g, latest = F.category_flows(hold, ["101"], ref)
    flows = g.set_index("instrument")["net_value_cr"]
    assert abs(flows["Stock S"]) < 1e-9            # the 1:10 split is not counted as buying
    assert flows["Stock Z"] == pytest.approx(15.0) and flows["Stock Y"] == pytest.approx(-20.0)
    mix = F.asset_mix(hold, "101", cur, ref)
    assert mix["Cash & debt"] == pytest.approx(3.0) and mix["Large cap"] == pytest.approx(10.0)


def test_nav_returns_calendar_periods():
    idx = pd.date_range("2020-01-01", "2026-01-01", freq="D")
    nav = pd.DataFrame({"a": np.linspace(100, 200, len(idx))}, index=idx)
    r = F.nav_returns(nav).loc["a"]
    assert r["1y"] == pytest.approx(200 / nav["a"].asof(pd.Timestamp("2025-01-01")) - 1)
    assert r["5y"] == pytest.approx((200 / nav["a"].asof(pd.Timestamp("2021-01-01"))) ** 0.2 - 1)
    short = F.nav_returns(nav.loc["2025-06-01":]).loc["a"]
    assert np.isnan(short["1y"]) and np.isnan(short["3y"])


PAGE_DRIVER = r'''
import os, runpy, sys
sys.path[:0] = [r"{stubs}", r"{root}"]
os.chdir(r"{root}")
import streamlit as st
from pathlib import Path
from tracker import config, build
if not config.PRICES_FILE.exists():
    from tracker import demo; demo.generate()
build.ensure_database()
tmp = Path(r"{tmp}")
for name, fn in (("MF_NAV_FILE", "mf_nav.csv.gz"), ("MF_HOLDINGS_FILE", "mf_holdings.csv.gz"),
                 ("MF_FUNDS_FILE", "mf_funds.csv"), ("ISIN_FILE", "isin_reference.csv.gz")):
    setattr(config, name, tmp / fn)
for state in ({{}}, {{"_stub_no_drill": False}}):
    st.session_state.clear(); st.session_state.update(state)
    try:
        runpy.run_path("pages/7_Fund_Holdings.py", run_name="__main__")
    except (st.StopRun, st.SwitchPage):
        pass
print("OK")
'''


def test_fund_page_renders_on_fixture(fake_sources):
    F.refresh_funds(log=lambda *a: None)
    tmp = config.MF_NAV_FILE.parent
    env = {**os.environ, "TRACKER_DATA_MODE": "demo"}
    code = PAGE_DRIVER.format(stubs=ROOT / "tests" / "stubs", root=ROOT, tmp=tmp)
    res = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=600)
    assert res.returncode == 0 and "OK" in res.stdout, res.stdout[-3000:] + res.stderr[-3000:]
