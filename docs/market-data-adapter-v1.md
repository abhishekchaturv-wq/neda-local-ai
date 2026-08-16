# NEDA Market Data Adapter V1

## Goal
Introduce a broker-independent market-data boundary so NEDA's analytics/UI are not
coupled to Zerodha, TradingView, or any other vendor.

## Architecture

```text
MarketDataProvider
       |
       +-- DemoMarketDataProvider   <-- V1
       |
       +-- ZerodhaProvider          <-- future
       |
       +-- OtherProvider            <-- future
```

The trading UI now asks the provider for a `MarketSnapshot` and passes its options
to the existing `options_chain.analyze_chain()` module.

## V1 guarantees
- Deterministic demo data remains available.
- Existing Options Engine V1 and Options Chain V1 remain the analytics layer.
- Provider interface is isolated from broker-specific APIs.
- No live credentials.
- No live orders.
- No directional signal generation.

## Why this milestone matters
The next live-data implementation can replace only the provider:

```text
DemoMarketDataProvider -> ZerodhaProvider
```

without rewriting the chain analytics or UI.

## Next milestone
Build the first live provider against the selected market-data source, with explicit
connection status, timestamps, stale-data detection, and failure handling before
allowing live data to influence any trading decision.
