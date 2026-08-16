# NEDA Options Engine V1

First implementation of NEDA's derivatives-first specialization for stock, index, and commodity options.

Implemented: contract identity, asset class, call/put, expiry, strike, multiplier, bid/ask/last, volume, OI, change in OI, IV field, Greeks container, underlying price, intrinsic value, ATM/ITM/OTM classification, mid-price, and validation.

Safety boundary: no broker integration, order placement, position management, or execution.

Next: V2 option-chain analytics (OI, change in OI, volume, PCR, max pain, strike aggregation, ATM structure, expiry summaries).
