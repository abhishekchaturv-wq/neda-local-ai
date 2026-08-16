# TEST-016 — Delta BTC Live Data to Paper Buyer Flow

## Objective
Connect the existing Delta Exchange India public BTC option market-data adapter to the
paper execution layer while enforcing NEDA's permanent strategy boundary: **options buyer**.

## Implemented
- `paper_trading.py`
  - Adds `BuyerOnlyPaperExecutionAdapter`.
  - BUY orders can open/increase long option positions.
  - SELL orders can only reduce an existing long position.
  - SELL-to-open is explicitly rejected.
- `tests/test_delta_paper_buyer_flow.py`
  - Delta snapshot feeds a paper BUY.
  - SELL-to-open is rejected.
  - SELL-to-close is permitted.
  - Paper mode has zero broker calls.

## Safety
This milestone does not implement live order placement, authentication, account access,
or broker execution. Delta public REST data is read-only.

## Verification
The TEST-016 suite is deterministic and mocks the public Delta response. A passing test
therefore proves the adapter/execution contract, not live Internet availability.

## Exit criteria
1. Buyer-only policy is enforced in code and tests.
2. A Delta BTC option snapshot can feed a paper BUY.
3. A paper exit can close a long position.
4. Short option opening is rejected.
5. No broker order call is possible through the TEST-016 adapter.
