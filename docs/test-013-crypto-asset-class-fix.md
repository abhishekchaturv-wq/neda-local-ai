# TEST-013 — Crypto Asset Class Fix

## Problem found during TEST-012 verification

BTC support in `market_data.py` correctly attempted to classify BTC option
contracts as `AssetClass.CRYPTO`, but the existing Options Engine V1 enum
contained only `STOCK`, `INDEX`, and `COMMODITY`.

This caused BTC tests to fail with:

`AttributeError: type object 'AssetClass' has no attribute 'CRYPTO'`

## Fix

Add `CRYPTO` as a first-class `AssetClass` value.

This is preferable to misclassifying BTC options as an index or commodity.

## Scope

- BTC options model support only.
- No live BTC market data.
- No broker connection.
- No order execution.
- Existing NIFTY/index behavior remains unchanged.

## Acceptance

The crypto asset-class tests must pass, followed by the existing TEST-012
market-data and trading-UI tests.
