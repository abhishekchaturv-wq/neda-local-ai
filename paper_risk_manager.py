"""TEST-018 buyer-focused paper risk and position management.

This module is a decision gate only. It does not submit broker orders and does
not modify the strategy automatically.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class RiskAction(str, Enum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    EXIT = "EXIT"


@dataclass(frozen=True)
class RiskConfig:
    starting_capital: float = 100000.0
    max_premium_per_trade: float = 0.02
    max_total_premium: float = 0.08
    max_positions: int = 3
    daily_loss_limit: float = 0.03
    max_consecutive_losses: int = 3
    stop_loss_pct: float = 0.35
    take_profit_pct: float = 0.75
    min_dte_for_new_entry: int = 3
    exit_dte: int = 1

    def __post_init__(self):
        if self.starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        for name in ("max_premium_per_trade", "max_total_premium",
                     "daily_loss_limit", "stop_loss_pct", "take_profit_pct"):
            value = getattr(self, name)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_positions <= 0 or self.max_consecutive_losses <= 0:
            raise ValueError("position/loss limits must be positive")
        if self.exit_dte < 0 or self.min_dte_for_new_entry < 0:
            raise ValueError("DTE limits cannot be negative")


@dataclass(frozen=True)
class RiskState:
    realized_pnl_today: float = 0.0
    open_premium: float = 0.0
    open_positions: int = 0
    consecutive_losses: int = 0


@dataclass(frozen=True)
class EntryRequest:
    premium: float
    dte: int


@dataclass(frozen=True)
class PositionRisk:
    entry_premium: float
    current_premium: float
    dte: int


@dataclass(frozen=True)
class RiskDecision:
    action: RiskAction
    reason: str
    max_loss_budget: float = 0.0


class BuyerRiskManager:
    """Hard risk gate for paper option buying.

    BUY entries are permitted only when all limits pass. Existing long
    positions can be exited. No short-option entry is represented here.
    """

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    @property
    def daily_loss_budget(self) -> float:
        return self.config.starting_capital * self.config.daily_loss_limit

    @property
    def per_trade_budget(self) -> float:
        return self.config.starting_capital * self.config.max_premium_per_trade

    @property
    def total_premium_budget(self) -> float:
        return self.config.starting_capital * self.config.max_total_premium

    def evaluate_entry(self, request: EntryRequest, state: RiskState) -> RiskDecision:
        if request.premium <= 0:
            return RiskDecision(RiskAction.REJECT, "INVALID_PREMIUM")
        if request.dte < self.config.min_dte_for_new_entry:
            return RiskDecision(RiskAction.REJECT, "ENTRY_TOO_CLOSE_TO_EXPIRY")
        if state.realized_pnl_today <= -self.daily_loss_budget:
            return RiskDecision(RiskAction.REJECT, "DAILY_LOSS_LIMIT_REACHED")
        if state.consecutive_losses >= self.config.max_consecutive_losses:
            return RiskDecision(RiskAction.REJECT, "CONSECUTIVE_LOSS_LIMIT_REACHED")
        if state.open_positions >= self.config.max_positions:
            return RiskDecision(RiskAction.REJECT, "MAX_OPEN_POSITIONS_REACHED")
        if request.premium > self.per_trade_budget:
            return RiskDecision(RiskAction.REJECT, "PER_TRADE_PREMIUM_LIMIT_EXCEEDED")
        if state.open_premium + request.premium > self.total_premium_budget:
            return RiskDecision(RiskAction.REJECT, "TOTAL_PREMIUM_LIMIT_EXCEEDED")
        return RiskDecision(RiskAction.ALLOW, "RISK_LIMITS_PASSED",
                            max_loss_budget=request.premium)

    def evaluate_position(self, position: PositionRisk) -> RiskDecision:
        if position.entry_premium <= 0 or position.current_premium < 0:
            return RiskDecision(RiskAction.REJECT, "INVALID_POSITION_MARK")
        change = (position.current_premium - position.entry_premium) / position.entry_premium
        if position.dte <= self.config.exit_dte:
            return RiskDecision(RiskAction.EXIT, "EXPIRY_PROTECTION")
        if change <= -self.config.stop_loss_pct:
            return RiskDecision(RiskAction.EXIT, "STOP_LOSS")
        if change >= self.config.take_profit_pct:
            return RiskDecision(RiskAction.EXIT, "TAKE_PROFIT")
        return RiskDecision(RiskAction.ALLOW, "POSITION_WITHIN_RISK_LIMITS")
