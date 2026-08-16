"""TEST-017 BTC options buyer strategy selector.

Pure decision layer: no broker/network execution and no order submission.
It selects a CALL/PUT candidate only when a directional market context,
liquidity, spread, moneyness and expiry conditions are satisfied.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from options_engine import OptionSnapshot, OptionType


class StrategyAction(str, Enum):
    BUY = "BUY"
    NO_TRADE = "NO_TRADE"


@dataclass(frozen=True)
class BuyerStrategyContext:
    """Normalized market context supplied by an upstream signal layer.

    trend_score and momentum_score are expected in [-1, 1].
    Positive values favor calls; negative values favor puts.
    """
    trend_score: float
    momentum_score: float

    def __post_init__(self):
        if not -1.0 <= self.trend_score <= 1.0:
            raise ValueError("trend_score must be between -1 and 1")
        if not -1.0 <= self.momentum_score <= 1.0:
            raise ValueError("momentum_score must be between -1 and 1")

    @property
    def directional_score(self) -> float:
        return 0.6 * self.trend_score + 0.4 * self.momentum_score


@dataclass(frozen=True)
class StrategyConfig:
    min_directional_score: float = 0.35
    max_spread_pct: float = 0.08
    min_volume: int = 1
    min_open_interest: int = 1
    min_dte: int = 3
    max_dte: int = 30
    max_otm_pct: float = 0.05
    min_premium: float = 1.0

    def __post_init__(self):
        if self.min_directional_score <= 0 or self.min_directional_score > 1:
            raise ValueError("invalid min_directional_score")
        if self.max_spread_pct <= 0:
            raise ValueError("invalid max_spread_pct")
        if self.min_dte < 0 or self.max_dte < self.min_dte:
            raise ValueError("invalid DTE range")


@dataclass(frozen=True)
class BuyerCandidate:
    symbol: str
    option_type: OptionType
    expiry: date
    strike: float
    premium: float
    score: float
    directional_score: float
    spread_pct: float
    dte: int
    reason: str


@dataclass(frozen=True)
class BuyerDecision:
    action: StrategyAction
    candidate: Optional[BuyerCandidate] = None
    reason: str = ""


class BTCOptionsBuyerStrategy:
    """Deterministic first-generation BTC options buyer selector.

    This is intentionally conservative. It does not place orders and it does
    not learn/change its parameters automatically.
    """

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    def evaluate(self, snapshots: list[OptionSnapshot],
                 context: BuyerStrategyContext,
                 as_of: date) -> BuyerDecision:
        direction = context.directional_score
        if abs(direction) < self.config.min_directional_score:
            return BuyerDecision(
                StrategyAction.NO_TRADE,
                reason="DIRECTIONAL_SIGNAL_TOO_WEAK",
            )

        desired = OptionType.CALL if direction > 0 else OptionType.PUT
        candidates = []

        for snap in snapshots:
            if snap.contract.option_type is not desired:
                continue

            dte = (snap.contract.expiry - as_of).days
            if dte < self.config.min_dte or dte > self.config.max_dte:
                continue

            bid, ask = snap.quote.bid, snap.quote.ask
            if bid is None or ask is None or ask <= 0 or bid < 0:
                continue

            spread_pct = (ask - bid) / ((ask + bid) / 2)
            if spread_pct > self.config.max_spread_pct:
                continue

            if (snap.quote.volume or 0) < self.config.min_volume:
                continue
            if (snap.quote.open_interest or 0) < self.config.min_open_interest:
                continue

            premium = ask
            if premium < self.config.min_premium:
                continue

            # For the first buyer strategy, avoid deep OTM lottery tickets.
            otm_pct = 0.0
            if snap.contract.option_type is OptionType.CALL:
                if snap.contract.strike > snap.underlying_price:
                    otm_pct = (snap.contract.strike - snap.underlying_price) / snap.underlying_price
            else:
                if snap.contract.strike < snap.underlying_price:
                    otm_pct = (snap.underlying_price - snap.contract.strike) / snap.underlying_price
            if otm_pct > self.config.max_otm_pct:
                continue

            # Higher is better. Direction is primary; liquidity and proximity
            # break ties. This score is for ranking, not a probability.
            spread_score = max(0.0, 1.0 - spread_pct / self.config.max_spread_pct)
            moneyness_score = max(0.0, 1.0 - otm_pct / self.config.max_otm_pct)
            dte_score = 1.0 - abs(dte - 14) / 16
            dte_score = max(0.0, min(1.0, dte_score))
            score = (
                0.50 * abs(direction)
                + 0.25 * spread_score
                + 0.15 * moneyness_score
                + 0.10 * dte_score
            )
            candidates.append(BuyerCandidate(
                symbol=snap.contract.key,
                option_type=desired,
                expiry=snap.contract.expiry,
                strike=snap.contract.strike,
                premium=premium,
                score=score,
                directional_score=direction,
                spread_pct=spread_pct,
                dte=dte,
                reason="DIRECTIONAL+LIQUIDITY+MONEYNESS+EXPIRY",
            ))

        if not candidates:
            return BuyerDecision(
                StrategyAction.NO_TRADE,
                reason="NO_QUALIFYING_OPTION_CANDIDATE",
            )

        best = max(candidates, key=lambda x: x.score)
        return BuyerDecision(StrategyAction.BUY, best, "QUALIFIED_BUYER_CANDIDATE")
