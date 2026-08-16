# TEST-021 — Persistent Paper Trading Session

This package extends TEST-020 into a restart-safe paper-trading session.

**Safety:** paper only, options buyer only, no broker execution, no autonomous strategy modification.

### New guarantees
- Persistent open-position state.
- Restart recovery.
- No duplicate entry while a position is open.
- Completed trades require an explicit `exit_reason`.
- Existing TEST-015 through TEST-020 behavior remains the regression baseline.

### Required verification
Run TEST-021 first, then the complete regression suite. Do not treat delivery success as verification success.
