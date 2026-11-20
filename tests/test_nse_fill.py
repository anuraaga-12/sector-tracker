"""NSE end-of-day fill: only empty cells are filled, Yahoo values win, holidays are skipped."""
from datetime import date

import numpy as np
import pandas as pd

from tracker import config, refresh
from tracker.providers import nse

FRI = date(2026, 11, 20)  # Friday


def _setup(monkeypatch, tmp_path, stocks: dict, indices: dict):
    monkeypatch.setattr(config, "REFRESH_LOG", tmp_path / "log.json")
    monkeypatch.setattr(nse, "stock_closes", lambda d: pd.Series(stocks.get(d, {}), dtype=float))
    monkeypatch.setattr(nse, "index_closes", lambda d: pd.Series(indices.get(d, {}), dtype=float))


def test_fills_missing_latest_day(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-11-18", "2026-11-19"])
    close = pd.DataFrame({"AAA": [10.0, 11.0], "BBB": [20.0, 21.0]}, index=idx)
    bench = pd.DataFrame({"^CRSLDX": [100.0, 101.0], "^NSEI": [50.0, 51.0]}, index=idx)
    _setup(monkeypatch, tmp_path,
           {FRI: {"AAA": 12.0, "BBB": 22.0, "ZZZ": 5.0}},
           {FRI: {"nifty 500": 102.0, "nifty 50": 52.0}})
    c, b = refresh.fill_recent_from_nse(close, bench, today=date(2026, 11, 21), log=lambda *a: None)
    assert c.index.max() == pd.Timestamp(FRI)
    assert c.loc[pd.Timestamp(FRI)].to_dict() == {"AAA": 12.0, "BBB": 22.0}  # untracked ZZZ not added
    assert b.loc[pd.Timestamp(FRI), "^CRSLDX"] == 102.0 and b.loc[pd.Timestamp(FRI), "^NSEI"] == 52.0
    assert c.loc[pd.Timestamp("2026-11-19"), "AAA"] == 11.0  # history untouched


def test_yahoo_values_win_and_only_gaps_filled(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-11-19", "2026-11-20"])
    close = pd.DataFrame({"AAA": [11.0, 12.5], "BBB": [21.0, np.nan]}, index=idx)
    bench = pd.DataFrame({"^CRSLDX": [101.0, 102.5], "^NSEI": [51.0, 52.5]}, index=idx)
    _setup(monkeypatch, tmp_path, {FRI: {"AAA": 99.0, "BBB": 22.0}}, {FRI: {"nifty 500": 999.0, "nifty 50": 999.0}})
    c, b = refresh.fill_recent_from_nse(close, bench, today=date(2026, 11, 21), log=lambda *a: None)
    assert c.loc[pd.Timestamp(FRI), "AAA"] == 12.5  # Yahoo kept
    assert c.loc[pd.Timestamp(FRI), "BBB"] == 22.0  # gap filled
    assert b.loc[pd.Timestamp(FRI), "^CRSLDX"] == 102.5


def test_holiday_or_unpublished_day_adds_nothing(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-11-19"])
    close = pd.DataFrame({"AAA": [11.0]}, index=idx)
    bench = pd.DataFrame({"^CRSLDX": [101.0]}, index=idx)
    _setup(monkeypatch, tmp_path, {}, {})
    c, b = refresh.fill_recent_from_nse(close, bench, today=date(2026, 11, 21), log=lambda *a: None)
    assert c.index.tolist() == close.index.tolist() and b.index.tolist() == bench.index.tolist()


def test_flags_symbols_missing_from_nse(monkeypatch, tmp_path):
    idx = pd.to_datetime(["2026-11-19", "2026-11-20"])
    close = pd.DataFrame({"AAA": [11.0, 12.0], "OLDNAME": [5.0, 5.0]}, index=idx)
    bench = pd.DataFrame({"^CRSLDX": [101.0, 102.0], "^NSEI": [51.0, 52.0]}, index=idx)
    _setup(monkeypatch, tmp_path, {FRI: {"AAA": 12.0}}, {})
    refresh.fill_recent_from_nse(close, bench, today=date(2026, 11, 21), log=lambda *a: None)
    from tracker import store
    entry = store.read_log()["nse_symbol_check"]
    assert entry["status"] == "warning" and "OLDNAME" in entry["detail"]
