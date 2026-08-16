# NEDA TEST-016
## Delta BTC Live-Data → Paper-Trading Buyer Flow

TEST-016 connects the existing Delta Exchange India public BTC options market-data adapter
to the paper execution layer.

### Hard strategy constraint
NEDA is an **options buyer**.

- BUY CALL / BUY PUT may open or increase a long option position.
- SELL is allowed only to reduce/close an existing long option position.
- SELL-to-open / naked option selling is rejected.
- No live broker order endpoint is used.
- The execution mode remains paper only.

### Scope
This milestone proves the data-to-paper execution plumbing using deterministic tests.
The unit tests mock Delta's public REST response; they do not claim that live network
connectivity was exercised during the test suite.

### Next
After TEST-016 is delivered and verified, the next layer should be the buyer-side trade
decision/risk engine: contract selection, premium budget, position sizing, entry rules,
profit-taking, stop-loss/expiry handling, and a persistent paper-trading journal.
