# TEST-020 — End-to-End Paper Trading Runner

Purpose: connect the already verified NEDA components into one paper-only trading cycle.

Flow:
Delta public BTC option data -> TEST-017 buyer strategy -> TEST-018 risk gate ->
TEST-016 buyer-only paper execution -> TEST-019 journal/feedback.

Safety:
- Paper trading only.
- BUY opens/increases long option positions.
- SELL only closes an existing long.
- No broker/order API.
- No automatic strategy modification.
- Every completed trade preserves signal, entry, selection and risk reasons.

Verification must prove the full path, no-trade behavior, risk rejection, paper exit,
journal creation, and broker_call_count == 0.
