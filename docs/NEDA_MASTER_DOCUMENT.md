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
The development workflow uses the existing local delivery pipeline:

`ZIP in ~/Downloads` → `NEDA Delivery Automation V2` → `~/Downloads/neda-delivery/inbox` + manifest → `NEDA Delivery Watcher V3` → isolated Git worktree → validation → commit → push to `origin/main`.

The watcher and automation are deliberately separate from the trading logic.

## Milestone history

### TEST-013 — Crypto asset-class fix
Verified successfully. Added/validated crypto option contract support.

### TEST-014 — Delivery concurrency reliability
Verified successfully. Hardened delivery flow for concurrent/overlapping deliveries.

### TEST-015 — Delta paper-trading foundation
Commit: `70897e6`
Verification: 5/5 Delta/paper tests passed; crypto, market-data and trading-UI regressions also passed.
Established broker-independent paper execution and Delta public market-data foundation.

### TEST-016 — Delta live-data paper buyer flow
Commit: `8a6aa6e`
Verification: 4/4 tests passed; TEST-015 and earlier regressions passed.
Established live Delta snapshot → paper buyer flow.
Buyer-only execution rejects SELL-to-open and permits SELL-to-close.
No live broker execution.

### TEST-017 — BTC options buyer strategy
Final verified commit: `42ee7cb`
Verification:
- Strategy: 6/6 passed
- TEST-016 regression: 4/4 passed
- TEST-015 regression: 5/5 passed
- Crypto regression: 3/3 passed

Strategy baseline:
- Directional score from trend/momentum.
- CALL for bullish direction; PUT for bearish direction.
- 3–30 DTE.
- Maximum 8% bid/ask spread.
- Minimum volume/open interest.
- Minimum premium.
- Maximum 5% OTM.
- Deterministic candidate scoring.
- No broker execution and no self-learning.

## TEST-018 — Buyer risk & position management
**Purpose:** add the hard risk gate before real paper trading begins.

Default baseline configuration:
- Starting paper capital: 100,000 units.
- Maximum premium per trade: 2% of starting capital.
- Maximum total open premium: 8%.
- Maximum simultaneous positions: 3.
- Daily realized-loss limit: 3%.
- Maximum consecutive losses before new entries: 3.
- Stop-loss: -35% on option premium.
- Take-profit: +75% on option premium.
- New entries require at least 3 DTE.
- Positions at 1 DTE or less trigger expiry protection.

TEST-018 is a **risk decision layer**, not a broker adapter. It cannot place live orders and does not change TEST-017 strategy parameters.

## Feedback-loop design
The feedback loop will be added only after a sufficient paper-trade sample exists.

Each paper trade should eventually record:
1. Market snapshot at signal time.
2. Directional score.
3. Selected option and alternatives.
4. Entry premium and spread.
5. DTE, moneyness, liquidity and open interest.
6. Risk decision.
7. Exit reason.
8. Maximum favorable/adverse excursion.
9. Realized P&L.
10. Slippage/fees assumptions.
11. Whether the signal was directionally correct.
12. Whether the option-selection decision helped or hurt.

The system should first **measure** performance. It must not automatically rewrite the strategy from a small sample. Changes should be proposed, tested on historical/replay data, and then paper-validated.

## Paper-trading readiness gate
Before sustained paper trading:
- TEST-018 risk manager verified.
- TEST-019 trade journal/feedback instrumentation verified.
- End-to-end live Delta public data → strategy → risk → paper execution verified.
- No live broker calls.
- Kill switch tested.
- State persistence/recovery tested.
- Basic replay/backtest validation completed.

## Future live-trading gate
Live execution must remain disabled until:
- broker/API permissions and order contracts are independently verified,
- paper performance is statistically meaningful,
- risk controls survive failure/recovery tests,
- execution reconciliation is tested,
- and explicit human approval is given.

**No live trading is implied by any current milestone.**
