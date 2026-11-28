import pandas as pd

from tracker import config, marketcap
from tracker.seed import load_taxonomy, load_universe


def test_taxonomy_integrity():
    tax = load_taxonomy()
    assert not tax.errors
    assert tax.sectors["sector_id"].is_unique and tax.subsectors["subsector_id"].is_unique
    assert set(tax.subsectors["sector_id"]) <= set(tax.sectors["sector_id"])
    p1 = set(tax.sectors.loc[tax.sectors["priority"] == 1, "sector_id"])
    assert {"PHARMA", "CAPGOODS", "FINSERV", "BANKING", "AUTO", "CHEM", "POWER", "INFRA", "DEFENCE", "RENEW"} <= p1


def test_universe_integrity():
    tax = load_taxonomy()
    uni = load_universe(valid_subsectors=set(tax.subsectors["subsector_id"]))
    assert not uni.errors, uni.errors
    assert uni.companies["nse_symbol"].is_unique
    prim = uni.classifications[uni.classifications["classification_type"] == "primary"]
    assert prim["nse_symbol"].is_unique                                   # exactly one primary each
    assert set(prim["nse_symbol"]) == set(uni.companies["nse_symbol"])
    used = set(uni.classifications["subsector_id"])
    assert used == set(tax.subsectors["subsector_id"]), "every sub-sector has at least one company"
    assert uni.classifications["classification_confidence"].isin(["High", "Medium", "Low"]).all()
    assert uni.classifications["source_reference"].notna().all()
    # spec-named examples are present in the right place
    c = uni.classifications
    assert c[(c["nse_symbol"] == "QPOWER") & (c["classification_type"] == "primary")]["subsector_id"].item() == "CG_XFANC"


def test_marketcap_indicative_and_amfi_precedence(tmp_path, monkeypatch):
    comps = pd.DataFrame({"nse_symbol": ["A", "B", "C", "D"], "isin": [None] * 4})
    quotes = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "market_cap_cr": [200000, 50000, 10000, 1000],
                           "as_of": ["2026-11-20"] * 4})
    out = marketcap.categorise(comps, quotes).set_index("nse_symbol")
    assert list(out["market_cap_category"]) == ["Large", "Mid", "Small", "Micro"]
    assert out["market_cap_category_source"].str.contains("Indicative").all()
    amfi = tmp_path / "amfi.csv"
    pd.DataFrame({"nse_symbol": ["B"], "category": ["Large Cap"], "as_of": ["2026-07-01"]}).to_csv(amfi, index=False)
    monkeypatch.setattr(config, "AMFI_FILE", amfi)
    out2 = marketcap.categorise(comps, quotes).set_index("nse_symbol")
    assert out2.loc["B", "market_cap_category"] == "Large"
    assert out2.loc["B", "market_cap_category_source"].startswith("AMFI")


def test_marketcap_uses_shares_times_latest_close():
    comps = pd.DataFrame({"nse_symbol": ["A"], "isin": [None]})
    quotes = pd.DataFrame({"symbol": ["A"], "market_cap_cr": [100.0], "shares": [1e7], "as_of": ["2026-11-01"]})
    last = pd.Series({"A": 250.0}, name=pd.Timestamp("2026-11-20"))
    out = marketcap.categorise(comps, quotes, last).set_index("nse_symbol")
    assert out.loc["A", "market_cap_cr"] == 250.0          # 1e7 shares × ₹250 = ₹250 cr
    assert out.loc["A", "market_cap_as_of"] == "2026-11-20"
