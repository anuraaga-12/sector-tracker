"""Market-data provider adapters.

Each adapter exposes the same small surface so a licensed provider can replace Yahoo later:

* ``download_close(tickers, start)``  -> wide DataFrame of adjusted closes
* ``download_ohlcv(ticker, period)``  -> OHLCV DataFrame for charts
* ``fetch_quote(ticker)``             -> dict with market cap / shares / ratios
* ``fetch_statements(ticker)``        -> dict of annual & quarterly income statements
"""
