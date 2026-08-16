"""TEST-021 persistent, restart-safe paper-trading session.

Builds on TEST-020 without introducing broker execution.  The session:
- polls the existing public Delta BTC provider;
- uses the verified buyer strategy/risk/execution/journal components;
- persists open-position state and completed journal records;
- never permits SELL-to-open;
- requires an explicit exit reason for every completed trade;
- does not modify strategy parameters automatically.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Optional

from btc_options_buyer_strategy import BuyerStrategyContext
from delta_market_data import DeltaBTCOptionProvider
from neda_test020_runner import EndToEndPaperTradingRunner, OpenPaperTrade, PaperRunResult
from paper_trade_journal import PaperTradeJournal, TradeRecord
from paper_risk_manager import RiskState


EXIT_REASONS = {
    "TAKE_PROFIT",
    "STOP_LOSS",
    "EXPIRY_PROTECTION",
    "SIGNAL_REVERSAL",
    "RISK_LIMIT",
    "DATA_SAFETY_EXIT",
    "SESSION_SHUTDOWN",
    "MANUAL_EXIT",
}


class PersistentPaperTradingSession:
    """Persistent wrapper around the verified TEST-020 runner."""

    VERSION = 1

    def __init__(
        self,
        state_path: str | Path,
        provider: DeltaBTCOptionProvider | None = None,
    ):
        self.state_path = Path(state_path)
        self.provider = provider or DeltaBTCOptionProvider()
        self.journal = PaperTradeJournal()
        self.runner = EndToEndPaperTradingRunner(
            provider=self.provider,
            journal=self.journal,
        )
        self._load()

    @property
    def open_trade(self) -> Optional[OpenPaperTrade]:
        return self.runner.open_trade

    def cycle(
        self,
        context: BuyerStrategyContext,
        quantity: float = 1.0,
        risk_state: RiskState | None = None,
        as_of: date | None = None,
    ) -> PaperRunResult:
        """Run one safe cycle.

        If a position exists, mark it from the latest public snapshot and
        either HOLD or SELL_TO_CLOSE with an explicit exit reason.
        Otherwise attempt one paper BUY.
        """
        if self.runner.open_trade is None:
            result = self.runner.run_once(
                context=context,
                quantity=quantity,
                risk_state=risk_state,
                as_of=as_of,
            )
        else:
            trade = self.runner.open_trade
            snapshot = self.provider.snapshot()
            mark = next(
                (s.quote.bid for s in snapshot.options
                 if s.contract.key == trade.symbol and s.quote.bid is not None),
                None,
            )
            snap = next(
                (s for s in snapshot.options if s.contract.key == trade.symbol),
                None,
            )
            if mark is None or snap is None:
                result = self.runner.mark_and_maybe_exit(
                    trade.entry_premium,
                    max(0, trade.entry_dte),
                )
            else:
                current_dte = (snap.contract.expiry - (as_of or date.today())).days
                result = self.runner.mark_and_maybe_exit(mark, current_dte)

        if result.action == "SELL_TO_CLOSE":
            if not result.risk_reason:
                raise ValueError("completed paper trade requires explicit exit_reason")
            if result.risk_reason not in EXIT_REASONS:
                raise ValueError(f"invalid exit reason: {result.risk_reason}")
        self.save()
        return result

    def close_with_reason(self, reason: str, current_premium: float, dte: int) -> PaperRunResult:
        """Explicitly close an open long position for a valid reason.

        This is intentionally narrow: it still uses the buyer-only paper
        adapter and therefore can only SELL-to-CLOSE an existing long.
        """
        if reason not in EXIT_REASONS:
            raise ValueError(f"invalid exit reason: {reason}")
        if self.runner.open_trade is None:
            raise RuntimeError("no open paper trade")
        result = self.runner.mark_and_maybe_exit(current_premium, dte)
        if result.action == "SELL_TO_CLOSE":
            self.save()
            return result
        # Risk manager did not request an exit; do not silently manufacture one.
        raise RuntimeError(
            f"risk manager did not authorize exit {reason}; returned {result.action}/{result.risk_reason}"
        )

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "version": self.VERSION,
            "open_trade": asdict(self.runner.open_trade) if self.runner.open_trade else None,
            "trade_counter": self.runner._trade_counter,
            "journal": [asdict(r) for r in self.journal.records()],
        }
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.state_path)

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if state.get("version") != self.VERSION:
            raise ValueError("unsupported TEST-021 state version")

        for row in state.get("journal", []):
            self.journal.record(TradeRecord(**row))

        raw = state.get("open_trade")
        if raw:
            self.runner.open_trade = OpenPaperTrade(**raw)
            self.runner._trade_counter = int(state.get("trade_counter", 0))
            # Restore the paper execution position so a restart cannot turn
            # a later SELL into a SELL-to-OPEN rejection/incorrect state.
            p = self.runner.execution.positions.setdefault(
                raw["symbol"],
                self.runner.execution.positions.get(raw["symbol"])
                or __import__("paper_trading").PaperPosition(raw["symbol"]),
            )
            p.quantity = float(raw["quantity"])
            p.average_entry = float(raw["entry_premium"])
        else:
            self.runner._trade_counter = int(state.get("trade_counter", 0))

    def broker_call_count(self) -> int:
        return self.runner.broker_call_count()
