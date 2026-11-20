"""Load and validate the curated taxonomy (YAML) and company universe (CSV)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from . import config

RATING_KEYS = {
    "growth": "Industry growth potential",
    "competition": "Competitive intensity",
    "barriers": "Entry barriers",
    "pricing": "Pricing power",
    "margins": "Margin stability",
    "roce": "Return on capital",
    "custconc": "Customer concentration",
    "cyclicality": "Cyclicality",
    "regulation": "Regulatory dependence",
    "export": "Export dependence",
    "structural": "Long-term structural relevance",
}
RATING_WORD = {"H": "High", "M": "Medium", "L": "Low"}
POSITION = {"L": "Leader", "E": "Established Player", "M": "Emerging Player", "N": "Niche Player"}
MODEL = {"MFG": "Manufacturing", "EPC": "EPC", "SVC": "Services", "DIST": "Distribution / Retail",
         "FIN": "Financial Services", "PLAT": "Platform", "UTIL": "Utility / Asset owner",
         "HOLD": "Holding company", "MIX": "Mixed"}
CONF = {"H": "High", "M": "Medium", "L": "Low"}
EXPOSURE_NOTE = {
    "Pure-play": "Pure-play (est. >80% of revenue)",
    "Majority": "Majority (est. 50-80%)",
    "Significant": "Significant (est. 20-50%)",
    "Minor": "Minor (est. <20%)",
}
SOURCE_V0 = ("Initial analyst mapping from public company business descriptions (v0.1, Nov-2026); "
             "to be verified against latest annual-report segment disclosure")


def parse_ratings(s: str | None) -> dict:
    out = {}
    for tok in (s or "").split():
        k, _, v = tok.partition(":")
        if k in RATING_KEYS and v in RATING_WORD:
            out[k] = RATING_WORD[v]
    return out


@dataclass
class Taxonomy:
    sectors: pd.DataFrame
    subsectors: pd.DataFrame
    errors: list = field(default_factory=list)


def load_taxonomy(directory: Path | None = None) -> Taxonomy:
    directory = Path(directory or config.TAXONOMY_DIR)
    sectors, subs, errors = [], [], []
    for f in sorted(directory.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        blocks = doc["sectors"] if "sectors" in doc else [doc]
        for b in blocks:
            s = b["sector"]
            sectors.append({
                "sector_id": s["id"], "sector_name": s["name"], "priority": s.get("priority", 2),
                "benchmark": s.get("benchmark"), "description": s.get("description", ""),
                "value_chain": s.get("value_chain", ""),
            })
            for ss in b.get("subsectors", []):
                profile = {k: v for k, v in ss.items() if k not in ("id", "name", "what", "chain", "rate")}
                profile["ratings"] = parse_ratings(ss.get("rate"))
                subs.append({
                    "subsector_id": ss["id"], "sector_id": s["id"], "subsector_name": ss["name"],
                    "description": ss.get("what", ""), "value_chain_position": ss.get("chain", ""),
                    "profile_json": json.dumps(profile, ensure_ascii=False),
                })
    sec = pd.DataFrame(sectors)
    sub = pd.DataFrame(subs)
    for col, df in (("sector_id", sec), ("subsector_id", sub)):
        d = df[df[col].duplicated()][col].tolist()
        if d:
            errors.append(f"Duplicate {col}: {d}")
    return Taxonomy(sec, sub, errors)


@dataclass
class Universe:
    companies: pd.DataFrame
    classifications: pd.DataFrame
    errors: list = field(default_factory=list)


def load_universe(directory: Path | None = None, valid_subsectors: set | None = None) -> Universe:
    directory = Path(directory or config.UNIVERSE_DIR)
    frames = []
    for f in sorted(directory.glob("*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        df["_file"] = f.name
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)
    errors = []
    raw["symbol"] = raw["symbol"].str.strip().str.upper()
    dups = raw[raw["symbol"].duplicated(keep=False)]
    if not dups.empty:
        errors.append(f"Duplicate symbols: {sorted(dups['symbol'].unique())}")
        raw = raw.drop_duplicates("symbol", keep="first")

    companies = pd.DataFrame({
        "nse_symbol": raw["symbol"],
        "company_name": raw["name"].str.strip(),
        "bse_code": None, "isin": None, "listing_status": "Mainboard",
        "business_model": raw["model"].map(MODEL).fillna(raw["model"]),
        "market_position": raw["position"].map(POSITION).fillna(raw["position"]),
        "primary_business": raw["business"],
        "customer_industry": raw["customers"],
    }).reset_index(drop=True)

    # Optional master-data override (ISIN, BSE code, listing status) supplied by the user
    if config.COMPANY_OVERRIDE.exists():
        ov = pd.read_csv(config.COMPANY_OVERRIDE, dtype=str, keep_default_na=False)
        ov["nse_symbol"] = ov["nse_symbol"].str.upper()
        companies = companies.merge(ov, on="nse_symbol", how="left", suffixes=("", "_ov"))
        for c in ("bse_code", "isin", "listing_status", "company_name"):
            if f"{c}_ov" in companies:
                companies[c] = companies[f"{c}_ov"].where(companies[f"{c}_ov"].astype(str).str.len() > 0, companies[c])
                companies = companies.drop(columns=f"{c}_ov")

    rows = []
    for _, r in raw.iterrows():
        conf = CONF.get(r["confidence"], "Low")
        base = {"nse_symbol": r["symbol"], "classification_confidence": conf,
                "source_reference": SOURCE_V0, "rationale": r["business"], "last_verified": None}
        rows.append({**base, "subsector_id": r["primary"], "classification_type": "primary",
                     "revenue_exposure": EXPOSURE_NOTE.get(r["exposure"], r["exposure"] or None)})
        for s in filter(None, r["secondary"].split("|")):
            rows.append({**base, "subsector_id": s, "classification_type": "secondary",
                         "revenue_exposure": "Material secondary exposure (unquantified)"})
        for s in filter(None, r["indirect"].split("|")):
            rows.append({**base, "subsector_id": s, "classification_type": "indirect",
                         "revenue_exposure": "Indirect / minor exposure",
                         "classification_confidence": "Low" if conf == "Low" else "Medium"})
    cls = pd.DataFrame(rows)
    # a company may not be mapped twice to the same sub-sector; keep the strongest type
    order = {"primary": 0, "secondary": 1, "indirect": 2}
    cls["_o"] = cls["classification_type"].map(order)
    dup_cls = cls[cls.duplicated(["nse_symbol", "subsector_id"], keep=False)]
    if not dup_cls.empty:
        errors.append("Repeated company/sub-sector mapping resolved to strongest type: "
                      + ", ".join(sorted(set(dup_cls["nse_symbol"]))))
    cls = cls.sort_values("_o").drop_duplicates(["nse_symbol", "subsector_id"]).drop(columns="_o")
    # Optional verification log: nse_symbol,subsector_id,last_verified,source_reference,confidence[,revenue_exposure]
    if config.VERIFICATION_FILE.exists():
        ver = pd.read_csv(config.VERIFICATION_FILE, dtype=str, keep_default_na=False)
        ver["nse_symbol"] = ver["nse_symbol"].str.upper()
        cls = cls.merge(ver, on=["nse_symbol", "subsector_id"], how="left", suffixes=("", "_v"))
        for c, vc in (("last_verified", "last_verified_v"), ("source_reference", "source_reference_v"),
                      ("classification_confidence", "confidence"), ("revenue_exposure", "revenue_exposure_v")):
            if vc in cls:
                v = cls[vc].fillna("")
                if c == "classification_confidence":
                    v = v.map(lambda x: CONF.get(x, x))
                cls[c] = v.where(v.str.len() > 0, cls[c])
                cls = cls.drop(columns=vc)
    if valid_subsectors is not None:
        bad = cls[~cls["subsector_id"].isin(valid_subsectors)]
        if not bad.empty:
            errors.append(f"Unknown sub-sector ids: {sorted(set(bad['subsector_id']))}")
            cls = cls[cls["subsector_id"].isin(valid_subsectors)]
    return Universe(companies, cls.reset_index(drop=True), errors)
