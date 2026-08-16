# TEST-024 FIX v2

Fixes the historical pagination test and logic.

A page having fewer than 1000 records is NOT treated as the end of the
requested historical window. TEST-024 continues requesting older data until
the requested start boundary is reached.

Risk-rejected strategy candidates are explicitly audited as RISK_REJECTED.
