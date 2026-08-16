"""NEDA Options Chain Analytics V1.

Dependency-light analytics for stock, index, and commodity option chains.
The module calculates descriptive chain statistics; it deliberately does not
declare a directional signal from OI or OI change alone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from options_engine import OptionSnapshot, OptionType


@dataclass(frozen=True)
class StrikeSummary:
    strike: float
    call_oi: int = 0
    put_oi: int = 0
    call_change_oi: int = 0
    put_change_oi: int = 0
    call_volume: int = 0
    put_volume: int = 0


@dataclass(frozen=True)
class ChainAnalytics:
    call_oi: int
    put_oi: int
    call_change_oi: int
    put_change_oi: int
    call_volume: int
    put_volume: int
    pcr_oi: Optional[float]
    pcr_volume: Optional[float]
    max_pain: Optional[float]
    strikes: tuple[StrikeSummary, ...]


def _nonnegative_int(value, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be a non-negative integer or None")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _quote_metric(snapshot: OptionSnapshot, field: str) -> int:
    return _nonnegative_int(getattr(snapshot.quote, field), field)


def _group_by_strike(snapshots: Iterable[OptionSnapshot]) -> dict[float, StrikeSummary]:
    grouped: dict[float, dict[str, int]] = {}

    for snapshot in snapshots:
        strike = float(snapshot.contract.strike)
        bucket = grouped.setdefault(
            strike,
            {
                "call_oi": 0, "put_oi": 0,
                "call_change_oi": 0, "put_change_oi": 0,
                "call_volume": 0, "put_volume": 0,
            },
        )

        prefix = "call" if snapshot.contract.option_type is OptionType.CALL else "put"
        bucket[f"{prefix}_oi"] += _quote_metric(snapshot, "open_interest")
        bucket[f"{prefix}_change_oi"] += _nonnegative_int(
            snapshot.quote.change_in_open_interest,
            "change_in_open_interest",
        ) if snapshot.quote.change_in_open_interest is not None else 0
        bucket[f"{prefix}_volume"] += _quote_metric(snapshot, "volume")

    return {
        strike: StrikeSummary(strike=strike, **values)
        for strike, values in sorted(grouped.items())
    }


def _max_pain(snapshots: list[OptionSnapshot]) -> Optional[float]:
    strikes = sorted({float(s.contract.strike) for s in snapshots})
    if not strikes:
        return None

    # For each candidate settlement strike, calculate total intrinsic loss
    # borne by option writers using the available OI.
    best_strike = None
    best_pain = None

    for settlement in strikes:
        pain = 0.0
        for s in snapshots:
            oi = _quote_metric(s, "open_interest")
            if oi == 0:
                continue
            if s.contract.option_type is OptionType.CALL:
                pain += max(0.0, settlement - s.contract.strike) * oi
            else:
                pain += max(0.0, s.contract.strike - settlement) * oi

        if best_pain is None or pain < best_pain:
            best_pain = pain
            best_strike = settlement

    return best_strike


def analyze_chain(snapshots: Iterable[OptionSnapshot]) -> ChainAnalytics:
    """Aggregate a single-expiry option chain.

    The caller should provide a coherent chain (same underlying and expiry).
    This function intentionally performs descriptive aggregation only.
    """
    items = list(snapshots)

    call_oi = put_oi = call_change = put_change = call_volume = put_volume = 0

    for s in items:
        if s.contract.option_type is OptionType.CALL:
            call_oi += _quote_metric(s, "open_interest")
            call_change += _nonnegative_int(
                s.quote.change_in_open_interest, "change_in_open_interest"
            ) if s.quote.change_in_open_interest is not None else 0
            call_volume += _quote_metric(s, "volume")
        else:
            put_oi += _quote_metric(s, "open_interest")
            put_change += _nonnegative_int(
                s.quote.change_in_open_interest, "change_in_open_interest"
            ) if s.quote.change_in_open_interest is not None else 0
            put_volume += _quote_metric(s, "volume")

    pcr_oi = put_oi / call_oi if call_oi else None
    pcr_volume = put_volume / call_volume if call_volume else None

    grouped = _group_by_strike(items)

    return ChainAnalytics(
        call_oi=call_oi,
        put_oi=put_oi,
        call_change_oi=call_change,
        put_change_oi=put_change,
        call_volume=call_volume,
        put_volume=put_volume,
        pcr_oi=pcr_oi,
        pcr_volume=pcr_volume,
        max_pain=_max_pain(items),
        strikes=tuple(grouped.values()),
    )
