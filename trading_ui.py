#!/usr/bin/env python3
"""NEDA Trading UI V1.1 with explicit market-data health state."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from market_data import DemoMarketDataProvider, MarketDataProvider
from options_chain import analyze_chain

APP_ROOT = Path(__file__).resolve().parent
WEB_ROOT = APP_ROOT / "web"

app = Flask(__name__)
market_data: MarketDataProvider = DemoMarketDataProvider()


def dashboard_payload(symbol: str = "NIFTY") -> dict:
    market = market_data.snapshot(symbol)
    analytics = analyze_chain(market.options)
    atm = min(
        market.options,
        key=lambda s: abs(s.contract.strike - market.underlying_price),
    ).contract.strike

    status = "STALE" if market.is_stale else ("LIVE" if market.live else "DEMO")

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
        "mode": "DEMO / PAPER ANALYSIS" if not market.live else "LIVE / PAPER ANALYSIS",
        "provider": market.provider_name,
        "data_status": status,
        "data_age_seconds": round(market.age_seconds, 2),
        "symbol": market.symbol,
        "asset_class": market.asset_class,
        "expiry": market.expiry.isoformat(),
        "spot": market.underlying_price,
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
            "reason": "Market-data foundation milestone: analytics remain descriptive and no directional signal is inferred from OI alone.",
        },
    }


@app.get("/")
def index():
    return send_from_directory(WEB_ROOT, "trading.html")


@app.get("/api/trading/chain")
def chain():
    symbol = request.args.get("symbol", "NIFTY")
    return jsonify(dashboard_payload(symbol))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8767, debug=False)
