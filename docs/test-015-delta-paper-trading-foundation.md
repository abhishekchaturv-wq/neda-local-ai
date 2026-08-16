# TEST-015 — Delta Exchange India BTC Paper Trading Foundation

## Objective
Use Delta Exchange India public market data for BTC options and add a broker-independent paper execution layer. **No live order API is implemented.**

## Delta boundary
Production REST: `https://api.india.delta.exchange`
Demo REST: `https://cdn-ind.testnet.deltaex.org`
Public BTC option-chain endpoint: `/v2/tickers?contract_types=call_options,put_options&underlying_asset_symbols=BTC` with optional `expiry_date`.
Public production WebSocket: `wss://public-socket.india.delta.exchange`.
Demo public WebSocket: `wss://socket-ind-pub.testnet.deltaex.org`.

## Paper rules
BUY fills at best ask; SELL fills at best bid. Non-crossing limits remain accepted. Missing quotes are rejected. Positions track quantity, average entry and realized/unrealized P&L.

## Safety
The paper adapter contains no API key, secret, HTTP client, order endpoint, cancel endpoint or broker execution method. `broker_call_count()` is permanently zero in this milestone.

## Next
After tests pass: public WebSocket streaming, reconnect/heartbeat, persistent paper audit trail, risk limits, then an extended paper-trading run. Live execution is explicitly out of scope until paper validation is complete.
