DATA ENGINEER TAKE-HOME — DATA PACKAGE
======================================

raw_feeds/
    Daily OHLCV market data for BTCUSD and ETHUSD from three venues
    (binance, kraken, coinbase) plus an external reference price feed.
    Column names and formats differ between venues. The data is real-world-
    shaped: it is not perfectly clean.

      binance_<ASSET>.csv     timestamp, open, high, low, close, volume
      kraken_<ASSET>.csv      date, open, high, low, close, volume
      coinbase_<ASSET>.csv    time, open, high, low, close, volume
      reference_<ASSET>.csv   date, reference_close_usd

new_source/
    A NEW venue ("gemini") in a DIFFERENT format from the others
    (epoch-millisecond timestamps, a combined symbol column, different
    column names). You'll be asked to onboard this source.

      gemini_<ASSET>.csv      symbol, time_ms, o, h, l, c, base_vol

starter_pipeline/
    An inherited loader (load_prices.py) plus its README. You'll fix and
    extend it.

Period is roughly 2026-01-01 to 2026-04-30, daily. All figures are
illustrative and generated for this exercise; they are not real prices.
