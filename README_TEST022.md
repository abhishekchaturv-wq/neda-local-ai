# NEDA TEST-022

Controlled live-data paper-trading session.

## Safety
This package is paper-only. It contains no broker API and must never place
real orders.

## Start
From `~/local-ai` after successful delivery:

    ~/local-ai/venv/bin/python neda_test022_live_paper_trading.py \
      --trend 0.60 \
      --momentum 0.55 \
      --cycles 30 \
      --interval 10

Use the existing TEST-017 context inputs; do not treat these example scores
as an automatic market signal.

## Verification
Run the TEST-022 suite and then the complete TEST-021..TEST-015 regression
chain before declaring the milestone verified.
