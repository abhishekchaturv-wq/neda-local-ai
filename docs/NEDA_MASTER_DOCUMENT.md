# NEDA — MASTER DEVELOPMENT & TRADING DOCUMENT

**Single source of truth for NEDA development, verification, architecture, paper-trading readiness and future live-trading readiness.**

## Core objective
NEDA is being built as a disciplined BTC options **buyer**, initially using Delta Exchange India market data and **paper trading only**. Live broker execution is not enabled.

## Non-negotiable strategy boundary
- Buy CALLs / buy PUTs.
- Never sell-to-open or establish naked short option positions.
- SELL is only for reducing/closing an existing long option position.
- No live broker execution during the paper-trading phase.
- No autonomous self-modification of strategy parameters.

## Delivery architecture
ZIP in `~/Downloads` → NEDA Delivery Automation V2 → `~/Downloads/neda-delivery/inbox` + manifest → NEDA Delivery Watcher V3 → isolated Git worktree → validation → commit → push to `origin/main`.

## Milestone history

### TEST-013 — Crypto asset-class fix
Verified successfully. Added/validated crypto option contract support.

### TEST-014 — Delivery concurrency reliability
Verified successfully. Hardened delivery flow for concurrent/overlapping deliveries.

### TEST-015 — Delta paper-trading foundation
Commit: `70897e6`
Verification: 5/5 Delta/paper tests passed; crypto, market-data and trading-UI regressions passed.
Established broker-independent paper execution and Delta public market-data foundation.

### TEST-016 — Delta live-data paper buyer flow
Commit: `8a6aa6e`
Verification: 4/4 tests passed; TEST-015 and earlier regressions passed.
Established live Delta snapshot → paper buyer flow.
Buyer-only execution rejects SELL-to-open and permits SELL-to-close.
No live broker execution.

### TEST-017 — BTC options buyer strategy
Final strategy commit: `42ee7cb`
Later documentation-status patch: `c6900af`
Verification: 6/6 strategy tests, 4/4 TEST-016, 5/5 TEST-015, 3/3 crypto regression tests passed.
Strategy rejects weak direction, wide spreads, low liquidity and deep OTM candidates; selects CALL in bullish context and PUT in bearish context.

### TEST-018 — Buyer risk & position management
Initial commit: `7fdcff9`
Fix: `0e26c04`
Final verification: 10/10 TEST-018 risk tests passed, plus all required regressions. All return codes were 0.

Risk baseline:
- Starting paper capital: 100,000 units.
- Maximum premium per trade: 2%.
- Maximum total open premium: 8%.
- Maximum simultaneous positions: 3.
- Daily realized-loss limit: 3%.
- Maximum consecutive losses before new entries: 3.
- Stop-loss: -35% on option premium.
- Take-profit: +75%.
- New entries require at least 3 DTE.
- Positions at 1 DTE or less trigger expiry protection.

### TEST-019 — Paper Trade Journal & Feedback Engine
Delivery commit: `a75aa57`
Final verification: 11/11 journal tests passed; all required regressions passed.
The journal records signal reason, **entry reason**, selection reason, risk reason, exit reason, P&L and MFE/MAE.
TEST-019 is observation-only and does not automatically modify strategy parameters.

### TEST-020 — End-to-End Paper Trading Runner
Initial commit: `e0ceda0`
Fix/final commit: `1dbcb2f`
Final verification: 3/3 TEST-020 tests passed plus the complete TEST-019 through market-data regression chain. All return codes were 0.
Established the verified single-cycle path:
Delta public data → buyer strategy → risk gate → buyer-only paper execution → journal.
The intermediate monitoring state is `HOLD`; an actual close is `SELL_TO_CLOSE`.
No live broker execution.

### TEST-021 — Persistent Paper Trading Session
Final commit: `911278e`
Verification: 4/4 TEST-021 tests passed plus TEST-020 through TEST-015 and crypto/market-data regressions. All return codes were 0.
Established restart-safe open-position persistence, duplicate-entry protection and explicit exit-reason enforcement for completed trades.

### TEST-022 — Controlled Live-Data Paper-Trading Session
**Implementation milestone; verification pending.**

Purpose:
- Run repeated paper-only cycles against the public Delta BTC option snapshot.
- Preserve TEST-017 strategy, TEST-018 risk, TEST-019 journal and TEST-021 persistence.
- Audit every `NO_TRADE`, `BUY`, `HOLD` and `SELL_TO_CLOSE` decision.
- Keep signal reason, entry reason, selection reason, risk reason and exit reason distinct.
- Assert that broker call count remains zero.

TEST-022 is an operational paper-trading milestone. It does **not** enable live trading and does not introduce automatic strategy learning.

## Feedback-loop design
The loop is:

Market snapshot → strategy signal → option selection → risk gate → paper entry → paper monitoring → paper exit → journal → outcome analysis → hypothesis → offline/replay test → controlled paper validation.

The first feedback phase should measure:
1. Directional accuracy.
2. Option-selection quality.
3. Entry spread/slippage.
4. DTE and moneyness effects.
5. Liquidity effects.
6. Stop-loss/take-profit behavior.
7. Maximum favorable/adverse excursion.
8. Expected value and win rate.
9. Performance by market regime.

NEDA should **not automatically learn from a single trade or small sample**. Strategy changes must be explicit, testable and paper-validated.

## Paper-trading readiness gate
Before sustained paper trading:
- TEST-018 verified.
- TEST-019 journal/feedback instrumentation verified.
- TEST-020 end-to-end live Delta public data → TEST-017 strategy → TEST-018 risk → paper execution → TEST-019 journal verified.
- TEST-021 persistence/recovery verified.
- TEST-022 controlled live-data session verified.
- No live broker calls.
- Kill switch tested.
- State persistence/recovery tested.
- Basic replay/backtest validation completed.

## Future live-trading gate
Live execution remains disabled until broker/API permissions and order contracts, paper performance, risk controls, reconciliation and failure recovery are independently verified and explicit human approval is given.

**No current milestone enables live trading.**
