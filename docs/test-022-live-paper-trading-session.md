# TEST-022 — Controlled Live-Data Paper-Trading Session

## Purpose
TEST-022 is the first operational paper-trading session milestone. It runs
repeated cycles against the public Delta BTC option snapshot while preserving
the verified TEST-017 strategy, TEST-018 risk controls, TEST-019 journal and
TEST-021 persistence layer.

**No live broker execution is present or permitted.**

## Decision audit
Every cycle records:
- action: `NO_TRADE`, `BUY`, `HOLD`, or `SELL_TO_CLOSE`;
- decision/signal reason;
- entry reason;
- contract selection reason;
- risk reason;
- trade ID;
- symbol;
- order status and simulated fill price;
- human-readable message;
- timestamp.

Completed trades continue to require an explicit exit reason through TEST-021.

## Runtime
The operator supplies the TEST-017 trend and momentum context explicitly.
This milestone does not invent a new signal-generation model or modify
strategy parameters automatically.

Example controlled run:

    ~/local-ai/venv/bin/python neda_test022_live_paper_trading.py \
      --trend 0.60 \
      --momentum 0.55 \
      --cycles 30 \
      --interval 10

The default state file is `~/.neda/test022_state.json` and the decision log is
`~/.neda/test022_decisions.jsonl`.

## Safety requirements
- Buyer-only options.
- SELL is only for reducing an existing long.
- No broker/order API.
- Broker call count must remain zero.
- State is persisted.
- Duplicate entries are prevented by TEST-021.
- Completed trades require an exit reason.
- No automatic strategy learning or parameter changes.

## TEST-022 acceptance gate
Before calling TEST-022 verified:
1. All TEST-022 tests pass.
2. TEST-021 through TEST-015 regressions pass.
3. A controlled live-data session produces auditable decision rows.
4. A paper BUY/HOLD/SELL lifecycle is observed where market conditions
   actually qualify; otherwise `NO_TRADE` is valid and must be recorded.
5. Restart recovery is demonstrated.
6. Broker call count remains zero.
7. The master document is updated with the verification result.

TEST-022 does not enable live trading.
