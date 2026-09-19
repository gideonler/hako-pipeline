"""Read, normalize, validate, deduplicate, and publish source files."""

import csv
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .adapters import parse_reference_row
from .database import upsert_candles, upsert_reference_prices
from .models import Candle, ReferencePrice
from .validation import validate_candle, validate_reference_price


logger = logging.getLogger(__name__)

CandleParser = Callable[[dict[str, str], str, int, str], Candle]


@dataclass(frozen=True)
class RejectedRow:
    """A source row that did not qualify for the trusted table."""

    source_file: str
    source_row_number: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class LoadResult:
    """Counts and rejection details from one source-file load."""

    rows_read: int
    accepted: int
    duplicates: int
    rejected: int
    written: int
    rejections: tuple[RejectedRow, ...]


def _candle_payload(candle: Candle) -> tuple[float | str, ...]:
    """Return values used to decide whether duplicate keys are identical."""
    return (
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
        candle.volume_unit,
    )


def load_ohlcv_file(
    db_path: Path,
    source_path: Path,
    symbol: str,
    parser: CandleParser,
) -> LoadResult:
    """Load one venue OHLCV file into the trusted table."""
    rows_read = 0
    duplicates = 0
    rejected_rows: list[RejectedRow] = []
    candles_by_key: dict[tuple[str, str, date], Candle] = {}
    conflicting_keys: set[tuple[str, str, date]] = set()

    with source_path.open(newline="", encoding="utf-8") as source:
        for source_row_number, row in enumerate(csv.DictReader(source), start=2):
            rows_read += 1

            try:
                candle = parser(
                    row,
                    source_path.name,
                    source_row_number,
                    symbol,
                )
            except (KeyError, TypeError, ValueError) as error:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        (f"parse_error:{type(error).__name__}",),
                    )
                )
                continue

            errors = validate_candle(candle)
            if errors:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        tuple(errors),
                    )
                )
                continue

            key = candle.business_key
            if key in conflicting_keys:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        ("conflicting_business_key",),
                    )
                )
                continue

            existing = candles_by_key.get(key)
            if existing is None:
                candles_by_key[key] = candle
            elif _candle_payload(existing) == _candle_payload(candle):
                duplicates += 1
            else:
                del candles_by_key[key]
                conflicting_keys.add(key)
                rejected_rows.extend(
                    (
                        RejectedRow(
                            existing.source_file,
                            existing.source_row_number,
                            ("conflicting_business_key",),
                        ),
                        RejectedRow(
                            candle.source_file,
                            candle.source_row_number,
                            ("conflicting_business_key",),
                        ),
                    )
                )

    trusted_candles = list(candles_by_key.values())
    written = upsert_candles(db_path, trusted_candles)
    result = LoadResult(
        rows_read=rows_read,
        accepted=len(trusted_candles),
        duplicates=duplicates,
        rejected=len(rejected_rows),
        written=written,
        rejections=tuple(rejected_rows),
    )

    logger.info(
        "Loaded %s: read=%d accepted=%d duplicates=%d rejected=%d written=%d",
        source_path.name,
        result.rows_read,
        result.accepted,
        result.duplicates,
        result.rejected,
        result.written,
    )
    return result


def load_reference_file(
    db_path: Path,
    source_path: Path,
    symbol: str,
) -> LoadResult:
    """Load one external daily reference-price file."""
    rows_read = 0
    duplicates = 0
    rejected_rows: list[RejectedRow] = []
    references_by_key: dict[tuple[str, date], ReferencePrice] = {}
    conflicting_keys: set[tuple[str, date]] = set()

    with source_path.open(newline="", encoding="utf-8") as source:
        for source_row_number, row in enumerate(csv.DictReader(source), start=2):
            rows_read += 1

            try:
                reference = parse_reference_row(
                    row,
                    source_path.name,
                    source_row_number,
                    symbol,
                )
            except (KeyError, TypeError, ValueError) as error:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        (f"parse_error:{type(error).__name__}",),
                    )
                )
                continue

            errors = validate_reference_price(reference)
            if errors:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        tuple(errors),
                    )
                )
                continue

            key = reference.business_key
            if key in conflicting_keys:
                rejected_rows.append(
                    RejectedRow(
                        source_path.name,
                        source_row_number,
                        ("conflicting_business_key",),
                    )
                )
                continue

            existing = references_by_key.get(key)
            if existing is None:
                references_by_key[key] = reference
            elif existing.reference_close_usd == reference.reference_close_usd:
                duplicates += 1
            else:
                del references_by_key[key]
                conflicting_keys.add(key)
                rejected_rows.extend(
                    (
                        RejectedRow(
                            existing.source_file,
                            existing.source_row_number,
                            ("conflicting_business_key",),
                        ),
                        RejectedRow(
                            reference.source_file,
                            reference.source_row_number,
                            ("conflicting_business_key",),
                        ),
                    )
                )

    trusted_references = list(references_by_key.values())
    written = upsert_reference_prices(db_path, trusted_references)
    result = LoadResult(
        rows_read=rows_read,
        accepted=len(trusted_references),
        duplicates=duplicates,
        rejected=len(rejected_rows),
        written=written,
        rejections=tuple(rejected_rows),
    )

    logger.info(
        "Loaded %s: read=%d accepted=%d duplicates=%d rejected=%d written=%d",
        source_path.name,
        result.rows_read,
        result.accepted,
        result.duplicates,
        result.rejected,
        result.written,
    )
    return result
