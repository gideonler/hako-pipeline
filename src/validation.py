"""Shared data-quality rules for canonical records."""

import math

from .models import Candle, ReferencePrice


def validate_candle(candle: Candle) -> list[str]:
    """Return every validation failure found on a normalized candle."""
    errors: list[str] = []
    prices = (candle.open, candle.high, candle.low, candle.close)

    if not all(math.isfinite(value) for value in (*prices, candle.volume)):
        errors.append("non_finite_numeric_value")
        return errors

    if any(price <= 0 for price in prices):
        errors.append("non_positive_price")
    if candle.volume < 0:
        errors.append("negative_volume")
    if candle.high < max(candle.open, candle.close, candle.low):
        errors.append("high_below_candle_value")
    if candle.low > min(candle.open, candle.close, candle.high):
        errors.append("low_above_candle_value")

    return errors


def validate_reference_price(reference: ReferencePrice) -> list[str]:
    """Return every validation failure found on a reference price."""
    if not math.isfinite(reference.reference_close_usd):
        return ["non_finite_reference_price"]
    if reference.reference_close_usd <= 0:
        return ["non_positive_reference_price"]
    return []
