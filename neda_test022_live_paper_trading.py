"""TEST-022 controlled live-data paper-trading session.

Uses the verified TEST-021 persistent session and runs repeated paper-only
cycles against the public Delta BTC option snapshot. No broker API exists in
this module and no live order can be submitted.

The session deliberately requires strategy context to be supplied explicitly
(trend and momentum scores). It records every decision so that NO_TRADE,
BUY, HOLD and SELL_TO_CLOSE outcomes remain auditable.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

from btc_options_buyer_strategy import BuyerStrategyContext
from neda_test021_session import PersistentPaperTradingSession
from paper_risk_manager import RiskState


def decision_row(result, cycle_no: int) -> dict:
    return {
        "cycle": cycle_no,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": result.action,
        "trade_id": result.trade_id,
        "symbol": result.symbol,
        "decision_reason": result.decision_reason,
        "entry_reason": result.entry_reason,
        "selection_reason": result.selection_reason,
        "risk_reason": result.risk_reason,
        "order_status": result.order_status,
        "fill_price": result.fill_price,
        "message": result.message,
    }


def run_session(
    state_path: str | Path,
    log_path: str | Path,
    trend_score: float,
    momentum_score: float,
    quantity: float = 1.0,
    interval_seconds: float = 10.0,
    cycles: int = 1,
) -> list[dict]:
    if cycles <= 0:
        raise ValueError("cycles must be positive")
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")

    session = PersistentPaperTradingSession(state_path)
    context = BuyerStrategyContext(trend_score, momentum_score)
    rows: list[dict] = []

    log = Path(log_path)
    log.parent.mkdir(parents=True, exist_ok=True)

    for cycle_no in range(1, cycles + 1):
        result = session.cycle(
            context=context,
            quantity=quantity,
            risk_state=RiskState(),
            as_of=date.today(),
        )
        row = decision_row(result, cycle_no)
        rows.append(row)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

        print(json.dumps(row, sort_keys=True))

        if cycle_no < cycles:
            time.sleep(interval_seconds)

    # Hard safety assertion: TEST-022 cannot have broker execution.
    if session.broker_call_count() != 0:
        raise RuntimeError("SAFETY FAILURE: broker call count is non-zero")

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="NEDA TEST-022 paper-only live-data session")
    parser.add_argument("--state", default=str(Path.home() / ".neda" / "test022_state.json"))
    parser.add_argument("--log", default=str(Path.home() / ".neda" / "test022_decisions.jsonl"))
    parser.add_argument("--trend", type=float, required=True, help="TEST-017 trend score [-1,1]")
    parser.add_argument("--momentum", type=float, required=True, help="TEST-017 momentum score [-1,1]")
    parser.add_argument("--quantity", type=float, default=1.0)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--cycles", type=int, default=1)
    args = parser.parse_args()

    run_session(
        args.state, args.log, args.trend, args.momentum,
        args.quantity, args.interval, args.cycles
    )


if __name__ == "__main__":
    main()
