# TEST-017 — BTC Options Buyer Strategy Engine

## Final status
TEST-017 implementation was delivered through the existing NEDA Downloads -> Automation V2 ->
Watcher V3 -> Delivery V2 pipeline.

Initial delivery commit:
- `94d02ff` — TEST-017-BTC-OPTIONS-BUYER-STRATEGY

A corrected TEST-017 package was subsequently delivered and produced:
- `42ee7cb` — TEST-017-BTC-OPTIONS-BUYER-STRATEGY

The latest commit on `origin/main` is `42ee7cb`.

## Objective
Add the first deterministic strategy layer for NEDA's paper-only BTC options buyer.

## Hard strategy boundary
NEDA is an **options buyer**:
- BUY CALL / BUY PUT decisions only.
- SELL-to-open / naked option selling is not a strategy action.
- Existing buyer-only paper execution permits SELL only to reduce/close an existing long option position.
- No broker order is placed by the strategy.
- The strategy does not automatically rewrite or modify its own parameters.

## Initial entry filters
The TEST-017 baseline considers:
- directional signal strength
- matching CALL/PUT direction
- 3–30 days to expiry
- bid/ask availability
- maximum spread
- minimum volume
- minimum open interest
- minimum premium
- maximum 5% out-of-the-money exposure

Candidates are ranked using directional strength, spread quality, moneyness proximity and expiry proximity.

## Important limitation
TEST-017 is a deterministic strategy baseline, not a claim of profitability or a validated trading edge.
The following are still pending:
- full position/risk manager
- trade journal
- adaptive feedback loop
- historical backtest/replay validation
- walk-forward validation
- extended live-data paper trading

## Verification status
The delivery system reports TEST-017 as successfully pushed to `origin/main` at `42ee7cb`.

The local verification suite still needs to be run against the **latest `origin/main` at `42ee7cb`** before TEST-017 is marked fully verified.

## Acceptance tests intended
1. Bullish context selects CALL.
2. Bearish context selects PUT.
3. Weak directional signal returns NO_TRADE.
4. Wide spread is rejected.
5. Deep OTM contract is rejected.
6. Low liquidity is rejected.

## Next milestone
TEST-018 should add buyer-focused risk and position management:
- premium budget
- position sizing
- maximum open risk
- daily loss limit
- stop-loss / profit-target rules
- expiry/time-based protection
