"""TEST-019/021 paper-trade journal and feedback dataset."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    timestamp: str
    symbol: str
    option_type: str
    strike: float
    dte: int
    entry_premium: float
    exit_premium: Optional[float]
    quantity: float
    direction_score: float
    spread_pct: float
    volume: float
    open_interest: float
    signal_reason: str
    entry_reason: str
    selection_reason: str
    risk_reason: str
    exit_reason: Optional[str] = None
    realized_pnl: Optional[float] = None
    max_favorable_pnl: Optional[float] = None
    max_adverse_pnl: Optional[float] = None

    def __post_init__(self):
        if self.option_type not in {"CALL", "PUT"}:
            raise ValueError("option_type must be CALL or PUT")
        if self.entry_premium <= 0 or self.quantity <= 0:
            raise ValueError("entry_premium and quantity must be positive")
        if self.dte < 0:
            raise ValueError("dte cannot be negative")
        if self.spread_pct < 0:
            raise ValueError("spread_pct cannot be negative")
        completed = self.exit_premium is not None or self.realized_pnl is not None
        if completed and not self.exit_reason:
            raise ValueError("completed trade requires explicit exit_reason")

    @property
    def completed(self) -> bool:
        return self.exit_premium is not None and self.realized_pnl is not None

    @property
    def return_pct(self) -> Optional[float]:
        if not self.completed:
            return None
        return self.realized_pnl / (self.entry_premium * self.quantity) * 100


class PaperTradeJournal:
    def __init__(self):
        self._records: list[TradeRecord] = []

    def record(self, trade: TradeRecord) -> None:
        if any(x.trade_id == trade.trade_id for x in self._records):
            raise ValueError(f"duplicate trade_id: {trade.trade_id}")
        self._records.append(trade)

    def records(self) -> tuple[TradeRecord, ...]:
        return tuple(self._records)

    def completed(self) -> tuple[TradeRecord, ...]:
        return tuple(x for x in self._records if x.completed)

    def summary(self) -> dict:
        done = self.completed()
        wins = [x for x in done if x.realized_pnl > 0]
        losses = [x for x in done if x.realized_pnl < 0]
        pnl = sum(x.realized_pnl for x in done)
        return {
            "trades": len(done),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(done) if done else 0.0),
            "realized_pnl": pnl,
            "avg_pnl": (pnl / len(done) if done else 0.0),
            "avg_return_pct": (
                sum(x.return_pct for x in done) / len(done) if done else 0.0
            ),
        }

    def feedback_rows(self) -> list[dict]:
        return [asdict(x) for x in self.completed()]

    def export_json(self) -> str:
        return json_dumps(self.feedback_rows())


def json_dumps(rows: list[dict]) -> str:
    import json
    return json.dumps(rows, indent=2, sort_keys=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
