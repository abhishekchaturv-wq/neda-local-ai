#!/usr/bin/env python3
"""NEDA Trading UI V1.

Small local Flask application that exposes the existing Options Chain V1
analytics through a browser dashboard. V1 intentionally uses deterministic
demo-chain data and performs analysis only; it does not place orders.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from options_chain import analyze_chain
from options_engine import (
    AssetClass,
    OptionContract,
    OptionQuote,
    OptionSnapshot,
    OptionType,
)

APP_ROOT = Path(__file__).resolve().parent
WEB_ROOT = APP_ROOT / "web"

app = Flask(__name__)


def demo_snapshots() -> list[OptionSnapshot]:
    """Return a deterministic NIFTY-like chain for UI development/testing."""
    symbol = "NIFTY"
    expiry = date(2026, 8, 27)
    underlying = 24520.0
    rows = [
        (24200, 180000, 140000, 22000, 18000),
        (24300, 210000, 165000, 26000, 24000),
        (24400, 265000, 230000, 34000, 32000),
        (24500, 310000, 295000, 41000, 46000),
        (24600, 285000, 330000, 38000, 52000),
        (24700, 220000, 280000, 29000, 43000),
        (24800, 175000, 240000, 21000, 35000),
    ]
    snapshots = []
    for strike, call_oi, put_oi, call_vol, put_vol in rows:
        snapshots.extend([
            OptionSnapshot(
                OptionContract(symbol, AssetClass.INDEX, expiry, strike, OptionType.CALL),
                underlying,
                OptionQuote(last=max(5.0, underlying - strike + 80), volume=call_vol,
                            open_interest=call_oi, change_in_open_interest=call_oi // 20),
            ),
            OptionSnapshot(
                OptionContract(symbol, AssetClass.INDEX, expiry, strike, OptionType.PUT),
                underlying,
                OptionQuote(last=max(5.0, strike - underlying + 80), volume=put_vol,
                            open_interest=put_oi, change_in_open_interest=put_oi // 20),
            ),
        ])
    return snapshots


def dashboard_payload() -> dict:
    snapshots = demo_snapshots()
    analytics = analyze_chain(snapshots)
    atm = min(snapshots, key=lambda s: abs(s.contract.strike - s.underlying_price)).contract.strike

    strikes = [
        {
            "strike": s.strike,
            "call_oi": s.call_oi,
            "put_oi": s.put_oi,
            "call_change_oi": s.call_change_oi,
            "put_change_oi": s.put_change_oi,
            "call_volume": s.call_volume,
            "put_volume": s.put_volume,
        }
        for s in analytics.strikes
    ]

    return {
        "mode": "DEMO / PAPER ANALYSIS",
        "symbol": "NIFTY",
        "asset_class": "INDEX",
        "expiry": "2026-08-27",
        "spot": snapshots[0].underlying_price,
        "atm": atm,
        "analytics": {
            "call_oi": analytics.call_oi,
            "put_oi": analytics.put_oi,
            "call_change_oi": analytics.call_change_oi,
            "put_change_oi": analytics.put_change_oi,
            "call_volume": analytics.call_volume,
            "put_volume": analytics.put_volume,
            "pcr_oi": analytics.pcr_oi,
            "pcr_volume": analytics.pcr_volume,
            "max_pain": analytics.max_pain,
        },
        "strikes": strikes,
        "signal": {
            "state": "WAIT",
            "confidence": None,
            "reason": "V1 chain analytics are descriptive; no directional signal is inferred from OI alone.",
        },
    }


@app.get("/")
def index():
    return send_from_directory(WEB_ROOT, "trading.html")


@app.get("/api/trading/chain")
def chain():
    return jsonify(dashboard_payload())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8767, debug=False)
