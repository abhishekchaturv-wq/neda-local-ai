# NEDA TEST-024 FIX — Historical Pagination & Decision Audit

This fix addresses the first autonomous TEST-024 smoke-cycle findings.

## Fix 1 — Full requested historical window

Binance BTCUSDT hourly klines are capped at 1000 records per response.
TEST-024 now paginates backwards until the requested `--history-days`
window is covered, rather than silently using only the most recent 1000
candles.

The audit records:
- requested source/window
- `paginated=true`
- record count
- SHA-256 of all raw pages consumed
- canonical dataset SHA-256
- `synthetic=false`

## Fix 2 — Explicit risk rejection

When the strategy identifies a candidate but TEST-018 rejects it, the
audit now records:

- `decision_stage=RISK_REJECTED`
- `final_action_reason=RISK_REJECTED:<risk_reason>`

This removes ambiguity between "no signal" and "signal rejected by risk".

## Safety

This remains paper-only. The broker-call-count assertion remains zero.
No strategy parameters are modified automatically.

## Validation

TEST-024 adds regression coverage for multi-page historical retrieval and
explicit risk-rejection audit semantics.
