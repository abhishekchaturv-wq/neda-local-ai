# TEST-017 — BTC Options Buyer Strategy Engine

## Objective
Add the first deterministic strategy layer for NEDA's paper-only BTC options buyer.

## Strategy boundary
NEDA is an **options buyer**:
- BUY CALL / BUY PUT decisions only.
- No sell-to-open decision.
- No broker orders.
- No automatic self-modification.

## Initial entry filters
- Directional signal strength >= 0.35
- Direction determines CALL vs PUT
- 3–30 days to expiry
- Bid/ask required
- Spread <= 8%
- Minimum volume and open interest
- Premium >= 1.0
- Maximum 5% OTM

Candidates are ranked by directional strength, spread quality, moneyness proximity and expiry proximity.

## Important limitation
This is a deterministic baseline, not a proven profitable strategy. It does not include the full risk manager, trade journal, adaptive feedback loop or statistical validation.

## Verification
Six deterministic tests cover bullish CALL selection, bearish PUT selection, weak-signal NO_TRADE, wide-spread rejection, deep-OTM rejection and low-liquidity rejection.

The tests do not claim live-market profitability.

## Next milestone
TEST-018: buyer risk and position management — premium budget, sizing, maximum open risk, daily loss limits, stop/target rules and expiry protection.
