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
Final verification: **10/10 TEST-018 risk tests passed**, plus TEST-017 6/6, TEST-016 4/4, TEST-015 5/5, Crypto 3/3 and Market Data 5/5. All return codes were 0.

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

**FINAL VERIFICATION: PASSED**
- TEST-019 Journal: **11/11 passed**
- TEST-018 Risk regression: **10/10 passed**
- TEST-017 Strategy regression: **6/6 passed**
- TEST-016 Buyer regression: **4/4 passed**
- TEST-015 Paper regression: **5/5 passed**
- Crypto regression: **3/3 passed**
- Market Data regression: **5/5 passed**

All seven verification groups completed with `OK`; the verification worktree was removed successfully.

Records per completed paper trade include:
- timestamp and trade ID;
- BTC option type, strike and DTE;
- entry and exit premium;
- quantity;
- directional score;
- spread, volume and open interest;
- **signal reason** — why the directional setup was detected;
- **entry reason** — why NEDA actually decided to enter the trade;
- **selection reason** — why this specific option contract was selected;
- **risk decision reason** — why the risk gate permitted the entry;
- exit reason;
- realized P&L;
- maximum favorable/adverse P&L.

The decision chain is intentionally preserved as separate fields:

**Market conditions → Signal reason → Entry reason → Contract selection reason → Risk approval → Paper execution → Exit → Outcome**

TEST-019 is observation-only. It does not place broker orders and does not automatically modify strategy parameters.

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
- End-to-end live Delta public data → TEST-017 strategy → TEST-018 risk → paper execution → TEST-019 journal verified.
- No live broker calls.
- Kill switch tested.
- State persistence/recovery tested.
- Basic replay/backtest validation completed.

## Future live-trading gate
Live execution remains disabled until broker/API permissions and order contracts, paper performance, risk controls, reconciliation and failure recovery are independently verified and explicit human approval is given.

**No current milestone enables live trading.**
