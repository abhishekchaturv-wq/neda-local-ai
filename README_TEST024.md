# TEST-024 — Autonomous Live-Audited Paper Trading

TEST-024 is the final bridge before operating NEDA in paper trading.

## What changed

TEST-022 required manually supplied `--trend` and `--momentum` scores. TEST-024
removes that manual input.

Each cycle now does:

1. Fetch timestamped historical BTCUSDT 1-hour candles from a public source.
2. Hash the raw historical response and canonical dataset.
3. Fetch the live BTC option snapshot from the Delta Exchange India public REST API.
4. Capture and SHA-256 hash the exact raw Delta response consumed by the NEDA provider.
5. Derive TEST-017 trend and momentum from historical BTC plus the live BTC spot.
6. Pass those internally derived scores into the existing TEST-017 strategy.
7. Apply TEST-018 risk controls.
8. Use TEST-021 persistence and the existing paper execution/journal stack.
9. Write a complete audit record containing historical provenance, live
   provenance, derived context, action, reasons and broker call count.
10. Refuse to continue if the live source is unavailable or synthetic.

## Important boundary

This is **paper trading only**. There are no broker/account/order endpoints in
TEST-024. `broker_call_count` must remain zero.

Historical data is used to derive the current market context; this is not a
claim that NEDA has silently retrained or self-modified its strategy. Any true
parameter learning should be introduced as a separate, versioned and validated
research process.

## Run

After delivery and regression verification:

```bash
cd ~/local-ai
~/local-ai/venv/bin/python neda_test024_autonomous_paper_trading.py \
  --history-days 30 \
  --quantity 1 \
  --interval 60 \
  --cycles 20
```

Audit:

```bash
cat ~/.neda/test024_audit.jsonl
```

State:

```bash
cat ~/.neda/test024_state.json
```

Do not connect a broker API or provide broker credentials to this runner.
