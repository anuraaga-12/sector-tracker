# Data sources & standards

| Data | Source today | Refresh | Notes |
|---|---|---|---|
| Taxonomy & industry profiles | Curated YAML (`data/seed/taxonomy`) | On edit | Initial qualitative analyst view; edit freely |
| Company → sub-sector mapping | Curated CSV (`data/seed/universe`) | On edit | v0.1 from public business descriptions. Verify against annual-report segment disclosures, investor presentations and exchange filings, then record the evidence in `data/manual/classification_verification.csv` (see the `.example` file) — this sets `last_verified`, the source reference and confidence |
| Daily prices (adjusted) | Yahoo Finance via `yfinance` | Weekdays 19:00 + 22:30 IST | Unofficial API, rate-limited; check its terms before any non-personal use |
| Latest-day closes (fallback) | NSE official bhavcopy + index close files (nsearchives.nseindia.com) | Same runs, only for recent days Yahoo has not posted | Unadjusted; replaced by Yahoo values once posted |
| Benchmarks | Yahoo tickers `^NSEI`, `^CRSLDX` (Nifty 500) + sector indices | Daily | Unavailable sector tickers fall back to Nifty 500 |
| Shares outstanding / market cap | Yahoo `fast_info` | Weekly (shares); market cap = shares × daily close | |
| Fundamentals | Yahoo summary + annual statements (ROCE) | Weekly, names older than 30 days | Mixed TTM / latest-quarter growth; period & source shown everywhere; never estimated |
| Market-cap category | AMFI half-yearly list (import) → else indicative thresholds | Twice a year | AMFI list effective Aug-2026 used ~₹1,06,300 cr (large) / ~₹33,500 cr (mid) cut-offs |
| Financial statement charts | Yahoo statements, fetched live and cached 6 h | On view | |
| Mutual-fund NAVs | AMFI daily NAV file via mfapi.in (free, no key) | Every daily run | Direct-Growth plans; one low-cost index fund per category is the benchmark |
| Mutual-fund holdings | Each fund house's SEBI-mandated monthly portfolio disclosure, parsed by the open [fund-holdings-data](https://github.com/kushagra-agarwal-a/fund-holdings-data) archive | Checked every daily run; new month appears ~10 days after month-end | Last 6 months kept. If the archive stops updating, the page keeps the last disclosure and shows its date. Funds tracked are listed in `settings.yaml` → `funds` |
| ISIN → NSE symbol, size bucket | NSE `EQUITY_L.csv`, Nifty 100 and Nifty Midcap 150 constituent files | Weekly, or when new holdings arrive | Large = Nifty 100, Mid = Midcap 150, Small = other listed (approximates AMFI's list) |

Rules enforced in code: missing fields stay blank; provider failures keep the last good value and are flagged on the
Data Quality page; every number shown carries an as-of date; demo mode is visually flagged and cannot write to live
data folders.

Upgrading to a licensed feed: implement `download_close`, `download_ohlcv`, `fetch_quote`, `fetch_fundamentals`
and `fetch_statements` in a new module under `tracker/providers/` and switch the import in `tracker/refresh.py`.
