# NEDA Trading UI V1

## Purpose
First visible NEDA trading interface. It exposes the existing Options Engine V1 and
Options Chain V1 analytics through a local browser dashboard.

## V1 scope
- NIFTY-like deterministic demo chain
- Spot and ATM
- Call/Put OI, ΔOI and volume by strike
- PCR(OI)
- Max Pain
- Explicit WAIT state
- Paper-analysis/demo mode only
- No broker connection
- No live order placement
- No directional signal inferred from OI alone

## Run
From the NEDA repository:

```bash
python3 trading_ui.py
```

Open:

```text
http://127.0.0.1:8767
```

## Architecture
Browser -> trading_ui.py -> options_chain.analyze_chain() -> options_engine.py

The UI deliberately uses the already verified Options Chain V1 rather than duplicating
analytics in JavaScript.

## Next milestones
1. Connect a real market-data adapter.
2. Add expiry/symbol selection.
3. Add Greeks and IV.
4. Add TradingView signal ingestion.
5. Add NEDA signal scoring.
6. Add paper-trading state and audit trail.
7. Add backtesting.
8. Only later consider controlled broker integration.
