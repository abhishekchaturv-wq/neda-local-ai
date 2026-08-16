# TEST-009 — Options Chain V1 Test Fix

TEST-008 exposed a test-boundary mismatch rather than an analytics failure.

`OptionQuote` already rejects negative `open_interest` during construction.
The TEST-008 test incorrectly constructed `OptionQuote(open_interest=-1)`
outside the `assertRaises` block and therefore failed before reaching the
assertion.

TEST-009 moves that construction inside `assertRaises`.

No production options-chain behavior is changed by this delivery.
