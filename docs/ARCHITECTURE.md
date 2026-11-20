# Architecture

```
data/seed/taxonomy/*.yaml ─┐        (curated, version-controlled)
data/seed/universe/*.csv ──┤
data/manual/*.csv (opt.) ──┤                       ┌──────────────────────┐
                           ├─► tracker.build ─────►│ SQLite (derived DB)  │◄── dashboard/ + app.py + pages/
data/market/*  ────────────┘    │                  └──────────────────────┘        (Streamlit, read-only)
   ▲                            ├─ seed.py          (validate taxonomy / universe)
   │                            ├─ marketcap.py     (AMFI or indicative categories)
   │                            └─ analytics.py     (returns, indices, breadth, momentum, flags, snapshots)
   │
tracker.refresh  ◄── providers/yahoo.py (yfinance)  ← GitHub Action (weekdays 19:00 + 22:30 IST, Saturday weekly)
```

| Component (spec §8) | Module |
|---|---|
| 1 Company universe ingestion | `tracker/seed.py` (`load_universe`), `data/seed/universe/` |
| 2 Sector / sub-sector taxonomy | `tracker/seed.py` (`load_taxonomy`), `data/seed/taxonomy/` |
| 3 Classification engine | universe CSV → `company_classification` (primary / secondary / indirect, confidence, source) + `classification_history` diff log |
| 4 Historical price ingestion | `tracker/refresh.py` `refresh_prices` + `tracker/store.py` (incremental merge, split-adjustment detection) |
| 5 Market cap & classification | `tracker/marketcap.py` |
| 6 Financial data ingestion | `tracker/refresh.py` `refresh_fundamentals`, `providers/yahoo.py`, manual override CSV |
| 7 Performance & breadth | `tracker/analytics.py` |
| 8 Ranking & rotation engine | `analytics.momentum_components / score / add_flags`, month-end reconstruction + recorded snapshots |
| 9 Dashboard | `app.py`, `pages/`, `dashboard/common.py`, `dashboard/charts.py` |
| 10 Validation & refresh management | `tracker/quality.py`, `tests/`, refresh log, GitHub workflow |

**Why a derived DB?** Free hosts have ephemeral disks. Seeds and compressed market files live in git; the DB is
rebuilt in ~10 s whenever an input file is newer than the DB. The app therefore never needs a market-data call
to render, and a data refresh is simply "new files → redeploy".

**Why the `deploy` branch?** Daily price files would bloat git history. The workflow publishes code + data as a single
orphan commit (force-push), so the history of `deploy` is always one commit while `main` stays clean.

**Performance.** Group indices are computed for all 217 groups at once with matrix products; a full build over
~680 symbols × ~1,500 days with 38 snapshot dates takes ≈ 9 s on a laptop-class CPU.
