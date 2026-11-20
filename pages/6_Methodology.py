"""Methodology, definitions and limitations."""
from __future__ import annotations

import streamlit as st
import yaml

from dashboard import common as C
from tracker import config

C.setup("Methodology", "📐")
st.title("📐 Methodology")

st.markdown("""
### Classification
* **Three levels:** Sector → Sub-sector → Company. Companies can map to several sub-sectors as **primary**
  (main business), **secondary** (material but not main) or **indirect** (minor exposure).
* **Performance and breadth use primary + secondary** constituents (configurable in `settings.yaml`); indirect
  exposure is shown in the universe but never moves the numbers. Unique-company counts never double-count.
* **Exposure bands** (Pure-play >80%, Majority 50–80%, Significant 20–50%, Minor <20%) are *analyst estimates*, not
  reported segment figures. Every mapping carries a confidence level and a source reference; `last_verified` stays
  blank until checked against an annual report.

### Returns
* Adjusted end-of-day closes; trading-day offsets 1W=5, 1M=21, 3M=63, 6M=126, 1Y=252, 3Y=756, 5Y=1260. 3Y and 5Y are CAGR.
* **Equal-weighted (EW)** group index: average of constituents' daily returns, chained. Handles new listings naturally.
* **Cap-weighted (CW)** index: daily returns weighted by shares × previous close (shares assumed constant).
* **Median**: median constituent return over the period — the best guard against one giant stock distorting the picture.
* Daily moves beyond ±40% are treated as data errors in index maths.
* **Excess return** = EW return − benchmark return over the same window (Nifty 500, Nifty 50, sector index).

### Breadth
% of priced constituents with positive 3M return; beating Nifty 500 over 1M / 3M / 6M; above 50- and 200-DMA;
median 3M by market-cap category; share of the cap-weighted 3M gain contributed by the top-2 stocks.

### Momentum score (0–100)
Each component is a **percentile rank across eligible peers** (≥ minimum priced members):

| Component | Raw input |
|---|---|
| Relative | 0.2·excess 1M + 0.4·excess 3M + 0.4·excess 6M vs Nifty 500 |
| Absolute | average of EW 3M and 6M return |
| Consistency | share of 1W/1M/3M/6M/1Y horizons with positive excess return |
| Breadth | % of constituents beating Nifty 500 over 3M |
| MA breadth | average of % above 50-DMA and % above 200-DMA |

Score = weighted average of components (weights in `settings.yaml`, adjustable live on the Rotation page).
**It describes past relative price behaviour and is not a forecast or recommendation.**

### Signals
* **Improving / Weakening momentum** — score change vs ~1 month ago beyond the threshold.
* **Improving breadth** — % above 50-DMA up by ≥ threshold vs ~1 month ago.
* **Narrow leadership** — cap-weighted 3M return exceeds the median by ≥ threshold, or top-2 stocks contribute ≥70% of the gain.
* **Small caps leading** — small/micro median 3M return exceeds large/mid median by ≥ threshold.
* **Early strength** — score < 50 three months ago, ≥ 60 now, and beating Nifty 500 over 1M.

### Market-cap categories
AMFI's half-yearly list when imported (`python -m tracker.refresh amfi <file.xlsx>`); otherwise **indicative**
thresholds from `settings.yaml`, clearly labelled. "Micro" is a sub-bucket of Small below a configurable cap (not an
AMFI category). Market cap = shares outstanding (weekly) × latest close (daily).

### Look-ahead & survivorship
* Point-in-time calculations only use prices up to that date.
* Reconstructed historical snapshots use the **current** classification and universe (a known source of survivorship
  bias). "Recorded" snapshots, appended by the daily job, preserve what the tracker showed at the time.
* Classification changes are logged in `classification_history`; delisted / merged names should be kept with a
  non-Mainboard `listing_status` rather than deleted.

### Sources
Prices, shares and summary fundamentals: Yahoo Finance via the unofficial `yfinance` library (free, rate-limited;
replaceable by a licensed feed through `tracker/providers`). Classifications: analyst mapping from public company
descriptions, to be verified against annual-report segment disclosures, investor presentations and exchange filings.
""")

st.subheader("Current settings")
st.code(yaml.safe_dump(config.settings(), sort_keys=False), language="yaml")
