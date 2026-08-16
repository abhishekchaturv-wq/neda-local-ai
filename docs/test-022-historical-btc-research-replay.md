# TEST-022 — Historical BTC Research & Replay Engine

## Objective

Extend NEDA from live/public-data paper execution into a reproducible historical
research layer. Historical data must be real, timestamped and provenance-audited.
NEDA must never manufacture BTC prices or silently substitute demo data.

## Hard audit requirements

Every historical dataset must carry:

1. source name;
2. source URL/API endpoint;
3. retrieval timestamp;
4. SHA-256 of the raw source response/file;
5. SHA-256 of NEDA's canonical normalized dataset;
6. record count;
7. explicit `synthetic=false` provenance flag.

Replay refuses to run when any of these are absent or inconsistent.

Every replayed record receives an audit record containing:

- original market timestamp;
- source;
- source URL;
- raw-source hash;
- normalized-dataset hash;
- sequence number.

This creates a trace from a strategy decision back to the exact source dataset.

## Real-data rule

The first external BTC spot adapter uses the public Binance BTCUSDT kline
endpoint. It hashes the raw HTTP response before parsing and does not fall back
to fixtures, generated prices or cached demo data.

Historical BTC option-chain data is **not fabricated**. If a verified historical
options dataset is unavailable, NEDA must report that limitation rather than
inventing option quotes.

## Replay integrity

The replay engine rejects:

- empty datasets;
- duplicate timestamps;
- non-monotonic timestamps;
- invalid OHLC relationships;
- negative market values;
- raw-file hash mismatches;
- normalized-dataset hash mismatches;
- record-count mismatches;
- synthetic datasets;
- invalid research/validation splits.

## Walk-forward separation

Historical data is divided into:

**Research / in-sample → Validation / out-of-sample**

A strategy must not use validation observations while determining a research rule.

The same normalized dataset and same replay configuration must produce the same
deterministic replay hash.

## Intended NEDA chain

Historical source
→ provenance verification
→ normalization
→ replay
→ strategy signal
→ entry reason
→ contract selection
→ TEST-018 risk gate
→ simulated paper execution
→ TEST-019 journal
→ outcome analysis.

TEST-022 is research/replay only. It does not enable live broker execution.

## Acceptance criteria

TEST-022 is complete only when:

- real-source provenance is mandatory;
- raw and normalized hashes are recorded;
- synthetic/fallback data is rejected;
- timestamp integrity is enforced;
- research/validation separation is enforced;
- deterministic replay is demonstrated;
- each replayed observation can be traced to its source;
- historical option data is never fabricated;
- existing TEST-015 through TEST-021 regressions remain green.

## Important limitation

BTC spot history and BTC options history are different datasets. Passing the BTC
spot provenance audit does **not** prove historical options data is genuine.
Option-chain replay must receive its own source, hash and timestamp audit before
option-specific historical conclusions are trusted.
