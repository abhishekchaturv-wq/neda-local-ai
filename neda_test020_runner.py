"""TEST-020 end-to-end paper trading runner.

Connects the already-verified NEDA components:
Delta public market data -> buyer strategy -> buyer risk gate ->
buyer-only paper execution -> paper-trade journal.

This module has no broker/order API and cannot place live trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from btc_options_buyer_strategy import (
    BTCOptionsBuyerStrategy,
    BuyerStrategyContext,
    StrategyAction,
)
from delta_market_data import DeltaBTCOptionProvider
from paper_risk_manager import BuyerRiskManager, EntryRequest, RiskAction, RiskState, PositionRisk
from paper_trade_journal import PaperTradeJournal, TradeRecord, utc_now
from paper_trading import BuyerOnlyPaperExecutionAdapter, PaperOrderStatus, PaperSide


@dataclass(frozen=True)
class PaperRunResult:
    action: str
    trade_id: Optional[str]
    symbol: Optional[str]
    decision_reason: str
    entry_reason: Optional[str]
    selection_reason: Optional[str]
    risk_reason: Optional[str]
    order_status: Optional[str]
    fill_price: Optional[float]
    message: str


@dataclass
class OpenPaperTrade:
    trade_id: str
    symbol: str
    option_type: str
    strike: float
    quantity: float
    entry_premium: float
    entry_dte: int
    direction_score: float
    spread_pct: float
    volume: float
    open_interest: float
    signal_reason: str
    entry_reason: str
    selection_reason: str
    risk_reason: str
    max_favorable_pnl: float = 0.0
    max_adverse_pnl: float = 0.0


class EndToEndPaperTradingRunner:
    """Single-cycle paper runner; live broker execution is impossible by design."""

    def __init__(
        self,
        provider: DeltaBTCOptionProvider | None = None,
        strategy: BTCOptionsBuyerStrategy | None = None,
        risk_manager: BuyerRiskManager | None = None,
        execution: BuyerOnlyPaperExecutionAdapter | None = None,
        journal: PaperTradeJournal | None = None,
    ):
        self.provider = provider or DeltaBTCOptionProvider()
        self.strategy = strategy or BTCOptionsBuyerStrategy()
        self.risk_manager = risk_manager or BuyerRiskManager()
        self.execution = execution or BuyerOnlyPaperExecutionAdapter()
        self.journal = journal or PaperTradeJournal()
        self.open_trade: OpenPaperTrade | None = None
        self._trade_counter = 0

    def run_once(
        self,
        context: BuyerStrategyContext,
        quantity: float = 1.0,
        risk_state: RiskState | None = None,
        as_of: date | None = None,
    ) -> PaperRunResult:
        """Fetch live public Delta data and attempt at most one paper BUY."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.open_trade is not None:
            return PaperRunResult(
                "NO_TRADE", None, None, "POSITION_ALREADY_OPEN", None, None, None,
                None, None, "Existing paper position must be monitored/closed first."
            )

        snapshot = self.provider.snapshot()
        trade_date = as_of or date.today()
        decision = self.strategy.evaluate(
            [x for x in snapshot.options], context, trade_date
        )
        if decision.action is not StrategyAction.BUY:
            return PaperRunResult(
                "NO_TRADE", None, None, decision.reason, None, None, None,
                None, None, "Strategy produced no qualifying buyer candidate."
            )

        candidate = decision.candidate
        assert candidate is not None
        state = risk_state or RiskState()
        risk = self.risk_manager.evaluate_entry(
            EntryRequest(candidate.premium * quantity, candidate.dte), state
        )
        if risk.action is not RiskAction.ALLOW:
            return PaperRunResult(
                "NO_TRADE", None, candidate.symbol, decision.reason,
                decision.reason, candidate.reason, risk.reason,
                "REJECTED", None, "Risk gate rejected the paper entry."
            )

        bid = None
        ask = candidate.premium
        for snap in snapshot.options:
            if snap.contract.key == candidate.symbol:
                bid, ask = snap.quote.bid, snap.quote.ask
                break

        order = self.execution.submit(
            candidate.symbol, PaperSide.BUY, quantity, bid, ask, limit_price=ask
        )
        if order.status is not PaperOrderStatus.FILLED:
            return PaperRunResult(
                "NO_TRADE", None, candidate.symbol, decision.reason,
                decision.reason, candidate.reason, risk.reason,
                order.status.value, order.fill_price,
                "Paper order was not filled."
            )

        self._trade_counter += 1
        trade_id = f"TEST020-PAPER-{self._trade_counter:06d}"
        self.open_trade = OpenPaperTrade(
            trade_id=trade_id,
            symbol=candidate.symbol,
            option_type=candidate.option_type.value,
            strike=candidate.strike,
            quantity=quantity,
            entry_premium=order.fill_price,
            entry_dte=candidate.dte,
            direction_score=candidate.directional_score,
            spread_pct=candidate.spread_pct,
            volume=float(next(
                s.quote.volume or 0 for s in snapshot.options
                if s.contract.key == candidate.symbol
            )),
            open_interest=float(next(
                s.quote.open_interest or 0 for s in snapshot.options
                if s.contract.key == candidate.symbol
            )),
            signal_reason=decision.reason,
            entry_reason="QUALIFIED_BUYER_CANDIDATE",
            selection_reason=candidate.reason,
            risk_reason=risk.reason,
        )
        return PaperRunResult(
            "BUY", trade_id, candidate.symbol, decision.reason,
            "QUALIFIED_BUYER_CANDIDATE", candidate.reason, risk.reason,
            order.status.value, order.fill_price,
            "Paper BUY opened; no broker order was submitted."
        )

    def mark_and_maybe_exit(self, current_premium: float, dte: int) -> PaperRunResult:
        """Mark the open paper position and close it if the risk gate says EXIT."""
        if self.open_trade is None:
            raise RuntimeError("no open paper trade")
        if current_premium < 0:
            raise ValueError("current_premium must be non-negative")

        trade = self.open_trade
        unrealized = (current_premium - trade.entry_premium) * trade.quantity
        trade.max_favorable_pnl = max(trade.max_favorable_pnl, unrealized)
        trade.max_adverse_pnl = min(trade.max_adverse_pnl, unrealized)

        risk = self.risk_manager.evaluate_position(
            PositionRisk(trade.entry_premium, current_premium, dte)
        )
        if risk.action is not RiskAction.EXIT:
            return PaperRunResult(
                "HOLD", trade.trade_id, trade.symbol, "POSITION_MONITOR",
                None, None, risk.reason, None, current_premium,
                "Paper position remains open."
            )

        order = self.execution.submit(
            trade.symbol, PaperSide.SELL, trade.quantity,
            bid=current_premium, ask=current_premium, limit_price=current_premium
        )
        if order.status is not PaperOrderStatus.FILLED:
            raise RuntimeError(f"paper close failed: {order.reason}")

        realized = (order.fill_price - trade.entry_premium) * trade.quantity
        record = TradeRecord(
            trade_id=trade.trade_id,
            timestamp=utc_now(),
            symbol=trade.symbol,
            option_type=trade.option_type,
            strike=trade.strike,
            dte=dte,
            entry_premium=trade.entry_premium,
            exit_premium=order.fill_price,
            quantity=trade.quantity,
            direction_score=trade.direction_score,
            spread_pct=trade.spread_pct,
            volume=trade.volume,
            open_interest=trade.open_interest,
            signal_reason=trade.signal_reason,
            entry_reason=trade.entry_reason,
            selection_reason=trade.selection_reason,
            risk_reason=trade.risk_reason,
            exit_reason=risk.reason,
            realized_pnl=realized,
            max_favorable_pnl=trade.max_favorable_pnl,
            max_adverse_pnl=trade.max_adverse_pnl,
        )
        self.journal.record(record)
        self.open_trade = None
        return PaperRunResult(
            "SELL_TO_CLOSE", trade.trade_id, trade.symbol,
            trade.signal_reason, trade.entry_reason, trade.selection_reason,
            risk.reason, order.status.value, order.fill_price,
            "Paper position closed and journaled; no broker order was submitted."
        )

    def broker_call_count(self) -> int:
        return self.execution.broker_call_count()
