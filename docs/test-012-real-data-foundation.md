# TEST-012 — Trading UI Real-Data Foundation

## Goal
Make the trading UI ready for multiple option-trading underlyings, including
NIFTY and BTC, while adding explicit market-data health metadata.

Make the trading UI ready for a future live market-data adapter without
pretending the current demo provider is live.

## Changes

- MarketSnapshot now carries provider name, observed timestamp, live flag,
  and stale-after threshold.
- `age_seconds` and `is_stale` are calculated centrally.
- Trading UI exposes `provider`, `data_status`, and `data_age_seconds`.
- Current provider remains deterministic DemoMarketDataProvider.
- NIFTY is supported as an index-options demo instrument.
- BTC is supported as a crypto-options demo instrument.
- The UI API accepts `?symbol=NIFTY` or `?symbol=BTC`.
- No broker credentials or broker APIs are introduced.
- No order execution is introduced.
- Signal remains WAIT.

## Why this is the right boundary

The next live-data adapter should implement the existing MarketDataProvider
interface and return a MarketSnapshot. The UI and Options Chain analytics
then remain unchanged.

## Required future live-provider safeguards

A live provider must provide:
- timestamped data
- stale-data detection
- connection/error state
- explicit provider identity
- coherent underlying/expiry/option-chain data
- no silent fallback from live data to stale/demo data

## BTC live-data note

BTC options will require a crypto-options market-data source/broker adapter
with the appropriate contract conventions. The multi-asset interface is now
prepared for that adapter, but TEST-012 does not claim BTC live connectivity.

## Next milestone

Implement a real provider against the selected market-data source, initially
read-only and paper-analysis-only. Then add refresh timestamps and clear data
health indicators to the UI before using live data for any signal scoring.
