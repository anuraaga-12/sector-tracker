# 🇮🇳 Indian Equity Sector & Sub-sector Intelligence Tracker

A market-intelligence dashboard for spotting which **sectors and granular sub-sector themes** are leading the Indian
market, whether the move is **broad-based or driven by a few heavyweights**, and **which listed companies** (large to
micro) participate in each theme. Built with Python · Streamlit · Plotly · pandas · SQLite.

> Research tool — **not** a stock-recommendation engine. Momentum scores describe past relative price behaviour.

## What's inside (v0.1)

| | |
|---|---|
| Sectors | **25** (11 Priority-1 with full industry profiles, 14 Priority-2 with compact profiles) |
| Sub-sectors | **192**, each with what-it-does, value-chain position, customers, inputs, economics, barriers, structural drivers, structural-vs-cyclical note, risks and 11 attractiveness ratings |
| Companies | **683** unique NSE mainboard symbols |
| Mappings | **1,289** (683 primary · 563 secondary · 43 indirect), each with exposure band, confidence and source |
| Pages | Market Overview · Sector Explorer · Sub-sector Deep Dive · Company Explorer (Screener-style chart) · Sector Rotation · Data Quality · Methodology |

### Pages
* **Market Overview** – KPIs, leading / weakening / emerging themes, sector heatmap (EW / median / cap-weighted, absolute or vs Nifty 500), top-10 tables, improving breadth, narrow leadership.
* **Sector Explorer** – description, value chain, sub-sector table with returns / breadth / score, market-cap distribution, drivers & risks, sector vs Nifty 500 chart, drill-down.
* **Sub-sector Deep Dive** – industry profile & attractiveness, full company universe (filter by exposure / cap / confidence, pure-play vs diversified), returns (EW, cap-weighted, median, vs N500/N50), breadth, performance by cap bucket, score components, peer fundamentals table + ROCE-vs-P/E chart, value-chain map.
* **Company Explorer** – Screener-like page: key ratios grid, **candlestick / line chart with 20/50/200-DMA, volume, log scale, period buttons, compare vs Nifty 500 / sub-sector index / peers**, returns vs benchmarks, quarterly & annual financial charts, classification evidence, peers, links to Screener / NSE / TradingView.
* **Sector Rotation** – live-reweightable momentum leaderboard with rank 1M / 3M ago, RRG-style rotation map, rank history, monthly score heatmap, breadth trend, large-vs-small participation.
* **Data Quality** – freshness timestamps, missing / stale prices, missing market cap / fundamentals, low-confidence and unverified mappings, thin sub-sectors, duplicates, classification change log, CSV export / import, guarded refresh button.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m tracker.refresh daily        # first run downloads ~6y of prices for ~680 stocks (10-20 min)
python -m tracker.refresh weekly       # optional: shares outstanding + fundamentals (slower)
streamlit run app.py
```

Explore without network (synthetic data, loud banner):

```bash
TRACKER_DATA_MODE=demo python -m tracker.demo
TRACKER_DATA_MODE=demo streamlit run app.py
```

## Hosting (free) — recommended setup

**Streamlit Community Cloud + a scheduled GitHub Action**:

1. Push this folder to a GitHub repo (public or private).
2. In the repo: *Actions → refresh-data → Run workflow* with `task = weekly`. It downloads prices, shares and
   fundamentals, runs the tests, and force-pushes code + data to a `deploy` branch as one squashed commit (so daily
   data never bloats history). It then runs automatically every weekday at 17:15 IST and Saturday morning.
3. On [share.streamlit.io](https://share.streamlit.io) → *Create app* → choose the repo, **branch `deploy`**, main file
   `app.py`, Python 3.12. Every data push triggers a redeploy; the app rebuilds its SQLite DB on start (~10 s).
4. Optional: *App settings → Secrets* → `ADMIN_PASSWORD = "…"` to protect the in-app refresh button.

Alternatives: the included `Dockerfile` runs on Render / Railway / Fly.io / any VPS (`docker build -t tracker . &&
docker run -p 8501:8501 tracker`). Point the host at the `deploy` branch, or run the refresh CLI on a cron there.

## Refreshing data

| Command | What it does |
|---|---|
| `python -m tracker.refresh daily` | Incremental prices (auto full re-download for new names / split-adjustment changes) → rebuild → record snapshot |
| `python -m tracker.refresh weekly` | daily + shares outstanding + fundamentals for names older than 30 days |
| `python -m tracker.refresh prices --full` | Re-download full price history |
| `python -m tracker.refresh amfi AMFI.xlsx` | Import AMFI's half-yearly categorisation (replaces indicative thresholds) |
| `python -m tracker.refresh import-prices file.csv` | Manual fallback: long CSV `symbol,date,close` |
| `python -m tracker.build` | Rebuild the DB from seed + market files |
| `python -m pytest` | Engine tests, data-integrity tests and a smoke run of every page (147 page executions) |

## Adding companies or sub-sectors

* **Company** – add one row to the relevant `data/seed/universe/*.csv`:
  `symbol,name,primary,secondary,indirect,exposure,position,model,business,customers,confidence`
  (`secondary` / `indirect` are `|`-separated sub-sector ids; `exposure` ∈ Pure-play / Majority / Significant / Minor;
  `position` L/E/M/N; `confidence` H/M/L). One row per company across all files — the loader rejects duplicates.
* **ISIN / BSE code / listing status** – `data/manual/company_master_override.csv` with `nse_symbol,isin,bse_code,listing_status`.
* **Verification evidence** – after checking a mapping against filings, add a row to `data/manual/classification_verification.csv` (`nse_symbol,subsector_id,last_verified,source_reference,confidence,revenue_exposure`).
* **Sub-sector** – add an entry under the sector in `data/seed/taxonomy/*.yaml` (see existing entries for fields).
* **Sector** – add a new YAML file in `data/seed/taxonomy/`.
* **Data provider** – implement the four functions in `tracker/providers/yahoo.py` for another feed.
* **Indicator** – add a column in `tracker/analytics.group_stats`, the table in `tracker/db.py`, and display it.

Run `python -m pytest tests/test_seed_and_mcap.py` after edits — it validates ids, uniqueness and coverage.

## Known limitations (read before relying on numbers)

* **Classifications are v0.1 analyst mappings** from public business descriptions, not yet verified line-by-line
  against FY26 annual-report segment data (`last_verified` is blank everywhere; 45 companies are Low confidence).
  Exposure bands are estimates. Symbols for very recent listings (2025–26 IPOs, demergers) are marked lower confidence.
* **ISIN and BSE codes are not populated** (no verified source was available while building); add via the override file.
* **SME-listed companies are not covered** yet (optional layer planned).
* **Prices come from Yahoo Finance via `yfinance`** — free but unofficial, rate-limited (especially from cloud IPs),
  and not licensed for commercial redistribution. Swap in a licensed feed for anything beyond personal research.
  Fundamentals from Yahoo's summary mix TTM values with latest-quarter growth; the period/source is always shown.
* **Market cap** = shares outstanding (weekly) × latest close; category uses indicative thresholds
  (Large ≥ ₹1,06,300 cr, Mid ≥ ₹33,500 cr, Micro < ₹5,000 cr) until you import AMFI's list.
* **Survivorship**: reconstructed history uses today's universe and mapping. Recorded snapshots (from the daily job)
  and the classification change log start accumulating from your first deployment.
* Sector benchmark tickers on Yahoo may be missing for some indices; such sectors fall back to Nifty 500 only.
* Nothing is live: everything is end-of-day.

See `docs/` for architecture, schema and data-source details.
