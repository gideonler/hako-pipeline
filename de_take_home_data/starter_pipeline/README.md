# Inherited loader — load_prices.py

This is the original inherited entry point. It currently loads only Binance
BTCUSD into an unconstrained local `prices` table.

## Run it

Its original command expects the working directory to be this folder:

```
cd de_take_home_data/starter_pipeline
python3 load_prices.py
```

It creates `prices.db` in the current directory.

## Current problems

- Paths depend on the working directory.
- The table has no primary key or constraints.
- Reruns append duplicate rows.
- CSV values are not parsed or validated explicitly.
- There is no rejection audit or missing-date check.
- The format and Binance source are hardcoded.
- Failures can bypass `conn.close()`.
- It prints only a total count and does not load Gemini.

The parameter placeholders in its SQL are correct and should be retained.

## Required verification after fixing it

From the repository root:

```
python3 -m unittest discover -s tests -v
```

Run the loader twice and confirm that the second run produces no new trusted
rows. Then run the full test suite above. Source settings should come from
`src/helpers/config.py`, while format transformations remain in
`src/adapters.py`.
