# TEST-019 — Paper Trade Journal & Feedback Engine

Observation-only measurement layer for NEDA paper trading.

This corrected package explicitly records four distinct decision explanations:
- `signal_reason`: why the market setup generated a directional signal;
- `entry_reason`: why NEDA actually entered the trade;
- `selection_reason`: why the specific option contract was selected;
- `risk_reason`: why the risk gate allowed the entry.

This is required for the feedback loop and does not enable live broker execution or automatic strategy modification.

Run:
`python3 -m unittest tests/test_paper_trade_journal.py -v`
