# TEST-022 Historical BTC Research & Replay — Fix

Fixes the TEST-022 `DATASET_HASH_MISMATCH` verification failure.

Root cause:
CSV parsing converts OHLCV values to floats while the unit-test fixture can
contain integer literals. The previous canonical hash therefore treated
`100` and `100.0` differently.

Fix:
Canonical dataset hashing now normalizes all OHLCV numeric fields to floats
before serialization. The provenance checks remain mandatory.

No provenance check has been weakened or bypassed.
No synthetic data is accepted.
No broker/live-trading capability is enabled.

Verification target:
- TEST-022 historical replay: all tests pass
- TEST-021 through TEST-015 and crypto/market-data regressions remain green
