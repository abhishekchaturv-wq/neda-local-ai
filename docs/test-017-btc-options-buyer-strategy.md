# TEST-017 — BTC Options Buyer Strategy Engine

## Objective
Add the first deterministic strategy layer for NEDA's paper-only BTC options buyer.

## Strategy boundary
NEDA remains an **options buyer**:
- Strategy may produce BUY CALL or BUY PUT decisions.
- It never produces a sell-to-open decision.
- It does not submit broker orders.
- It does not change its own parameters or learn automatically.

## Initial entry filters
A candidate must satisfy:
- directional signal strength >= configured threshold
- option type matches direction: positive -> CALL, negative -> PUT
- 3–30 days to expiry
- bid/ask available
- spread <= 8%
- minimum volume and open interest
- premium >= configured minimum
- no more than 5% out-of-the-money

Candidates are ranked using directional strength, spread quality, moneyness proximity and expiry proximity.

## Important limitation
The initial strategy is a deterministic baseline, not a proven profitable strategy.
It does not yet include a full risk manager, trade journal, adaptive feedback loop, or
statistically validated edge.

## Verification
The TEST-017 suite covers:
1. bullish context -> CALL
2. bearish context -> PUT
3. weak direction -> NO_TRADE
4. wide spread rejection
5. deep OTM rejection
6. low liquidity rejection

## Next milestone
TEST-018 should add position/risk management: premium budget, sizing, max open risk,
daily loss limits, stop/target rules and expiry protection.
