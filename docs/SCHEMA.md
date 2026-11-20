# Database schema (SQLite, `data/tracker.db`)

Authoritative DDL: `tracker/db.py`. Foreign keys are enforced; indexes on sector, sub-sector and ISIN lookups.

| Table | Key | Purpose |
|---|---|---|
| `sectors` | sector_id | name, priority, Yahoo benchmark ticker, description, value chain |
| `subsectors` | subsector_id → sectors | name, description, value-chain position, `profile_json` (customers, inputs, economics, barriers, drivers, nature, risks, ratings) |
| `companies` | company_id, unique nse_symbol | name, bse_code, isin, listing_status, business model, market position, business description, customers, market_cap_cr, market_cap_category (+ source, as-of) |
| `company_classification` | (company_id, subsector_id) | classification_type ∈ primary/secondary/indirect, revenue_exposure band, confidence ∈ High/Medium/Low, source_reference, rationale, last_verified |
| `classification_history` | — | append-only log of added / removed / changed mappings |
| `historical_prices` | (company_id, date) | OHLCV cache (reserved for chart caching). Analytics use the compressed price matrix in `data/market/` |
| `stock_metrics` | company_id | latest close/date, 1W…5Y returns, 50/200-DMA and flags, 52-week high/low |
| `financial_metrics` | (company_id, reporting_period) | revenue, growth, EBITDA & margin, PAT & growth, ROCE, ROE, debt, D/E, P/E, P/B, EV/EBITDA, source, as_of |
| `group_performance` | (level, entity_id, calculation_date) | sector & sub-sector stats per date: EW / CW / median returns, excess vs N500 / N50 / sector index, breadth, cap-bucket medians, top-2 concentration, momentum components, score, rank, eligibility, flags |
| `sector_snapshots` | (date, level, entity, snapshot_type) | rank / score / breadth history; `reconstructed` (month-ends from prices) and `recorded` (written by the daily job) |
| `index_series` | (level, entity, weighting, date) | equal- and cap-weighted group index levels for charts |
| `refresh_log` | component | timestamps / status for prices, market cap, fundamentals, classification seed, build |

Spec-to-schema notes: the spec's `subsector_performance` table is `group_performance` (level = subsector), which also
stores sector-level rows; `breadth_metrics` are explicit columns rather than a blob; `valuation_metrics` are explicit
P/E, P/B, EV/EBITDA columns.
