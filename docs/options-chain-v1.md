# NEDA Options Chain Analytics V1

## Purpose

TEST-008 adds the first chain-level intelligence layer above `options_engine.py`.

It aggregates a coherent single-expiry chain for stock, index, or commodity
options and produces descriptive statistics that later layers can interpret.

## Implemented

- Call and put open-interest totals
- Call and put change-in-open-interest totals
- Call and put volume totals
- Put/Call Ratio (PCR) by open interest
- PCR by volume
- Strike-level OI, change-OI, and volume summaries
- Max-pain calculation using open interest
- Empty-chain handling
- Zero-denominator handling

## Interpretation boundary

This layer does **not** declare an OI or PCR reading bullish or bearish.

For NEDA's options-specialist goal, positioning must later be interpreted with
underlying price action, IV, volume, Greeks, expiry, and market structure.

## Data assumptions

`analyze_chain()` expects snapshots representing one coherent underlying and
expiry. It does not fetch market data and does not connect to a broker.

## Tests

Six unit tests cover:

1. Totals and PCR
2. Zero denominators
3. Max pain
4. Empty chains
5. Strike summaries
6. Invalid OI rejection

## Next layer

The next milestone is deeper positioning analytics:

- ATM-relative chain windows
- OI concentration
- change-OI concentration
- volume/OI diagnostics
- IV and skew integration
- expiry-aware interpretation
- structured setup scoring

## Execution boundary

No order placement, broker integration, position management, or live execution
is introduced by TEST-008.
