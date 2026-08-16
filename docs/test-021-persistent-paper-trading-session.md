# TEST-021 — Persistent Paper Trading Session

## Purpose
Extend the verified TEST-020 single-cycle runner into a restart-safe paper-trading session.

## Scope
- Public Delta BTC market data only.
- TEST-017 buyer strategy.
- TEST-018 buyer risk management.
- TEST-016 buyer-only paper execution.
- TEST-019 journal/feedback.
- Persistent state for open positions and completed trades.
- No broker/order API.
- No autonomous strategy changes.

## Mandatory decision chain
Market conditions → signal reason → entry reason → contract selection reason → risk approval → paper BUY → HOLD/monitor → exit decision → **explicit exit reason** → paper SELL-to-CLOSE → outcome.

## Exit reasons
`TAKE_PROFIT`, `STOP_LOSS`, `EXPIRY_PROTECTION`, `SIGNAL_REVERSAL`, `RISK_LIMIT`, `DATA_SAFETY_EXIT`, `SESSION_SHUTDOWN`, `MANUAL_EXIT`.

A completed trade without an exit reason is invalid and must be rejected.

## Persistence requirements
- State is written atomically.
- Open positions survive restart.
- Paper execution position is reconstructed on restart.
- Completed journal entries survive restart.
- Duplicate trade IDs remain rejected.
- An existing open position cannot create another entry.

## Safety requirements
- SELL-to-open remains forbidden.
- Stale/missing market data must not create a new entry.
- Kill-switch/risk rejection remains enforced by TEST-018.
- `broker_call_count()` must remain zero.
- Strategy parameters are not automatically modified.

## Verification
TEST-021 must verify persistence, restart recovery, duplicate-entry prevention, explicit exit-reason enforcement, buyer-only execution and no live broker execution, followed by the complete TEST-015 through TEST-020 regression suite.

## Documentation rule
Update `docs/NEDA_MASTER_DOCUMENT.md` in the same delivery. This remains the single master document.
