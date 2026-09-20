CREATE TABLE IF NOT EXISTS rejected_rows (
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    reasons TEXT NOT NULL,
    raw_record TEXT NOT NULL,
    PRIMARY KEY (source_file, source_row_number)
);

CREATE TABLE IF NOT EXISTS missing_dates (
    source_file TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    PRIMARY KEY (source_file, symbol, trading_date)
);

CREATE TABLE IF NOT EXISTS daily_ohlcv (
    venue TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    open REAL NOT NULL CHECK (open > 0),
    high REAL NOT NULL CHECK (high > 0),
    low REAL NOT NULL CHECK (low > 0),
    close REAL NOT NULL CHECK (close > 0),
    volume REAL NOT NULL CHECK (volume >= 0),
    volume_unit TEXT NOT NULL
        CHECK (volume_unit IN ('base', 'quote', 'unknown')),
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TEXT NOT NULL,

    PRIMARY KEY (venue, symbol, trading_date),

    CHECK (high >= low),
    CHECK (high >= open AND high >= close),
    CHECK (low <= open AND low <= close)
);

CREATE INDEX IF NOT EXISTS idx_daily_ohlcv_symbol_date
ON daily_ohlcv (symbol, trading_date);

CREATE TABLE IF NOT EXISTS daily_reference_price (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    reference_close_usd REAL NOT NULL
        CHECK (reference_close_usd > 0),
    source_file TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TEXT NOT NULL,

    PRIMARY KEY (symbol, trading_date)
);
