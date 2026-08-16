# TEST-014 — Delivery Concurrency Reliability

## Problem

The existing bridge returned shell exit code `0` when another delivery was
already running. The watcher interpreted any `0` result as successful delivery
and removed `DELIVERY_MANIFEST.json`.

This could produce a false `DELIVERY COMPLETED` event and permanently lose a
package before it was committed to Git.

## Fix

TEST-014 introduces an explicit delivery result contract:

- `0` = SUCCESS
- `10` = BUSY / RETRY
- other non-zero = FAILURE

The watcher now handles these states separately.

### SUCCESS

- Mark delivery successful.
- Archive the manifest.
- Remove the active manifest.

### BUSY / RETRY

- Keep the manifest.
- Do not report completion.
- Retry after the configured busy interval.

### FAILURE

- Keep the manifest.
- Report failure.
- Allow correction/retry.

## Why this matters

The delivery pipeline must be reliable before it is trusted for automated
development. A package must never disappear merely because another delivery
happened to be running.

## Scope

This milestone changes delivery orchestration only.

It does not change:

- NIFTY/BTC market data
- options calculations
- trading UI
- broker connectivity
- order execution

## Validation

The included tests verify the concurrency result-code contract, manifest
retention on busy, success-only manifest archival, and explicit bridge result
markers.

## Next

After TEST-014 is delivered and verified, re-deliver TEST-013 so that the
`CRYPTO` asset-class fix can reach `main`. Then re-run the complete NIFTY/BTC
TEST-012 regression suite.
