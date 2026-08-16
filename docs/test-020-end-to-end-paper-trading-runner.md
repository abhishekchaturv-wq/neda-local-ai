# TEST-020 — End-to-End Paper Trading Runner

## Objective
Integrate the verified TEST-015 through TEST-019 components into a single paper-only execution cycle.

## Decision chain
Live Delta public snapshot -> strategy signal -> contract selection -> risk approval ->
paper BUY -> monitoring -> paper SELL-to-close -> TEST-019 journal -> feedback dataset.

## Required safety boundaries
- BTC options buyer only.
- BUY CALL / BUY PUT only.
- SELL is only for reducing an existing long paper position.
- No live broker execution.
- No autonomous strategy changes.
- Risk limits remain enforced before entry and during position monitoring.

## Evidence captured per completed trade
- signal reason
- entry reason
- contract selection reason
- risk decision reason
- entry/exit premium
- DTE
- liquidity fields
- realized P&L
- maximum favorable/adverse P&L
- exit reason

## Verification gate
1. End-to-end BUY from a Delta-shaped snapshot.
2. Weak signal produces NO_TRADE.
3. Risk rejection produces NO_TRADE.
4. Position can be monitored without forced exit.
5. Risk-triggered exit produces SELL-to-close.
6. Completed trade appears in TEST-019 journal.
7. All decision-reason fields survive into feedback rows.
8. broker_call_count remains zero.

## Live trading status
Live execution remains disabled. TEST-020 does not authorize broker connectivity or real-money trading.
