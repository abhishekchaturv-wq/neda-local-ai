# TEST-023 — Final Live-Audited Paper Trading Gate

This is the final gate before sustained paper trading.

It enforces:
1. Real public BTC market-data acquisition.
2. No synthetic/demo fallback.
3. Raw-response SHA-256 provenance.
4. Source URL and observation timestamp.
5. Explicit rejection of missing provenance.
6. Paper-only action boundary.
7. Persistent session state.
8. Per-decision audit records.
9. Explicit signal, entry, selection and risk reasons.
10. Exit-reason field support.

IMPORTANT:
TEST-023 itself does not place broker orders. It is a final live-data/audit
boundary test. Existing TEST-017 through TEST-022 components remain the
decision and validation stack.

Pass condition:
- TEST-023 tests all pass.
- TEST-022 through TEST-015 regressions all pass.
- Live-source smoke test succeeds against the public BTC endpoint.
- Audit output contains a real source URL, observation timestamp, raw hash,
  and `synthetic=false`.

Only after those conditions are green should the sustained paper session be
started.
