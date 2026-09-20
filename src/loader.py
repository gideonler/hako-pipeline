"""Normalize full source snapshots, validate, and publish accepted records."""

import csv
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .adapters import parse_reference_row
from .database import database_session, upsert_candles, upsert_reference_prices
from .models import Candle, ReferencePrice
from .validation import validate_candle, validate_reference_price

logger = logging.getLogger(__name__)
CandleParser = Callable[[dict[str, str], str, int, str], Candle]
Record = Candle | ReferencePrice


@dataclass(frozen=True)
class RejectedRow:
    source_file: str
    source_row_number: int
    reasons: tuple[str, ...]
    raw_record: str = ""


@dataclass(frozen=True)
class LoadResult:
    rows_read: int
    accepted: int
    duplicates: int
    rejected: int
    written: int
    rejections: tuple[RejectedRow, ...]
    missing_dates: tuple[str, ...] = ()
    removed: int = 0


def _record_values(record: Record) -> tuple:
    """Return the values used to distinguish duplicates from conflicts."""
    if isinstance(record, Candle):
        return (
            record.open,
            record.high,
            record.low,
            record.close,
            record.volume,
            record.volume_unit,
        )
    return (record.reference_close_usd,)


def _read_source_file(source_path, symbol, parser, required_columns):
    """Parse a CSV and group its records by business key."""
    records_by_key = defaultdict(list)
    rejections = []
    seen_dates = set()
    rows_read = 0

    with source_path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        headers = set(reader.fieldnames or [])
        if not required_columns.issubset(headers):
            missing = ", ".join(sorted(required_columns - headers))
            raise ValueError(
                f"{source_path.name}: missing required columns: {missing}"
            )

        for source_row_number, row in enumerate(reader, start=2):
            rows_read += 1
            raw_record = json.dumps(row, sort_keys=True)
            try:
                if None in row:
                    raise ValueError("extra CSV fields")
                record = parser(
                    row,
                    source_path.name,
                    source_row_number,
                    symbol,
                )
            except (KeyError, TypeError, ValueError) as error:
                rejections.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        (f"parse_error:{error}",),
                        raw_record,
                    )
                )
                continue

            seen_dates.add(record.trading_date)
            records_by_key[record.business_key].append((record, raw_record))

    if rows_read == 0:
        raise ValueError(f"{source_path.name}: empty source file")

    return records_by_key, rejections, seen_dates, rows_read


def _calculate_missing_dates(seen_dates, expected_start, expected_end):
    """Return expected calendar dates that do not appear in the source."""
    if expected_start is None and expected_end is None:
        return ()
    if expected_start is None or expected_end is None:
        raise ValueError("expected_start and expected_end must be provided together")

    expected_dates = {
        expected_start + timedelta(days=offset)
        for offset in range((expected_end - expected_start).days + 1)
    }
    return tuple(
        missing_date.isoformat()
        for missing_date in sorted(expected_dates - seen_dates)
    )


def _validate_records(
    records_by_key,
    parse_rejections,
    source_file,
    symbol,
    validator,
    references,
    max_deviation,
    expected_start,
    expected_end,
):
    """Validate grouped records and separate accepted rows from rejections."""
    accepted = []
    rejections = list(parse_rejections)
    duplicates = 0

    for entries in records_by_key.values():
        record = entries[0][0]
        has_conflict = any(
            _record_values(other) != _record_values(record)
            for other, _ in entries[1:]
        )
        errors = ["conflicting_business_key"] if has_conflict else validator(record)

        if (
            expected_start is not None
            and expected_end is not None
            and not expected_start <= record.trading_date <= expected_end
        ):
            errors = [*errors, "date_outside_expected_period"]

        if not errors and references is not None:
            reference = references.get((symbol, record.trading_date.isoformat()))
            if reference is None:
                errors = ["missing_reference_price"]
            elif abs(record.close / reference - 1) > max_deviation:
                errors = ["reference_deviation_exceeds_threshold"]

        if errors:
            rejections.extend(
                RejectedRow(
                    source_file,
                    item.source_row_number,
                    tuple(errors),
                    raw_record,
                )
                for item, raw_record in entries
            )
        else:
            accepted.append(record)
            duplicates += len(entries) - 1

    return accepted, rejections, duplicates


def _publish_snapshot(database, table, source_file, symbol, accepted, writer):
    """Upsert accepted rows and remove obsolete rows from the same source file."""
    retained_dates = {
        record.trading_date.isoformat()
        for record in accepted
    }

    with database_session(database) as connection:
        existing_dates = {
            trading_date
            for (trading_date,) in connection.execute(
                f"SELECT trading_date FROM {table} "
                "WHERE source_file = ? AND symbol = ?",
                (source_file, symbol),
            )
        }
        obsolete_dates = existing_dates - retained_dates

        before_delete = connection.total_changes
        connection.executemany(
            f"DELETE FROM {table} "
            "WHERE source_file = ? AND symbol = ? AND trading_date = ?",
            [
                (source_file, symbol, trading_date)
                for trading_date in obsolete_dates
            ],
        )
        removed = connection.total_changes - before_delete
        written = writer(connection, accepted)

    return written, removed


def _load(
    database,
    source_path,
    symbol,
    parser,
    validator,
    writer,
    table,
    required_columns,
    references=None,
    max_deviation=0.20,
    expected_start=None,
    expected_end=None,
):
    """Normalize, validate, and publish one complete source snapshot."""
    if not 0 < max_deviation < 1:
        raise ValueError("max_deviation must be between zero and one")

    records_by_key, parse_rejections, seen_dates, rows_read = _read_source_file(
        source_path,
        symbol,
        parser,
        required_columns,
    )
    accepted, rejections, duplicates = _validate_records(
        records_by_key,
        parse_rejections,
        source_path.name,
        symbol,
        validator,
        references,
        max_deviation,
        expected_start,
        expected_end,
    )

    missing_dates = _calculate_missing_dates(
        seen_dates,
        expected_start,
        expected_end,
    )
    written, removed = _publish_snapshot(
        database,
        table,
        source_path.name,
        symbol,
        accepted,
        writer,
    )

    result = LoadResult(
        rows_read=rows_read,
        accepted=len(accepted),
        duplicates=duplicates,
        rejected=len(rejections),
        written=written,
        rejections=tuple(rejections),
        missing_dates=missing_dates,
        removed=removed,
    )
    logger.info(
        "%s: read=%d accepted=%d duplicates=%d rejected=%d written=%d removed=%d",
        source_path.name,
        result.rows_read,
        result.accepted,
        result.duplicates,
        result.rejected,
        result.written,
        result.removed,
    )
    return result


def load_ohlcv_file(
    database,
    source_path: Path,
    symbol: str,
    parser: CandleParser,
    *,
    required_columns: frozenset[str],
    references=None,
    max_deviation=0.20,
    expected_start=None,
    expected_end=None,
) -> LoadResult:
    """Load one venue OHLCV file into the trusted table."""
    return _load(
        database=database,
        source_path=source_path,
        symbol=symbol,
        parser=parser,
        validator=validate_candle,
        writer=upsert_candles,
        table="daily_ohlcv",
        required_columns=required_columns,
        references=references,
        max_deviation=max_deviation,
        expected_start=expected_start,
        expected_end=expected_end,
    )


def load_reference_file(
    database,
    source_path: Path,
    symbol: str,
    *,
    expected_start=None,
    expected_end=None,
) -> LoadResult:
    """Load one reference-price file into the trusted reference table."""
    return _load(
        database=database,
        source_path=source_path,
        symbol=symbol,
        parser=parse_reference_row,
        validator=validate_reference_price,
        writer=upsert_reference_prices,
        table="daily_reference_price",
        required_columns=frozenset({"date", "reference_close_usd"}),
        expected_start=expected_start,
        expected_end=expected_end,
    )
