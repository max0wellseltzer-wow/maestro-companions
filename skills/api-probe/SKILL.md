---
name: api-probe
description: Before building on any outside API, spend five minutes probing it for real - name mapping, all-or-nothing rejections, feed/plan differences, premium endpoints that refuse with HTTP 200, batch size, page size, speed - spending each probe from the live job's shared daily ledger, and save one trimmed real response as a test fixture that is checked for the real key value. Use before writing a client, adapter, cross-check or downloader for a new endpoint, when a free-plan answer is suspiciously small, and whenever an API detail would otherwise come from memory.
---

# api-probe

Three small probes on 2026-10-12 replaced a design that would have been wrong three ways. From memory, Alpaca's daily
bars "just work"; measured: one invalid symbol rejects the whole request, the free IEX feed carries 3-6% of the market's
volume (wrong for volume), and 2,000 symbols fit one request in 3.6 s (a whole-universe year in minutes, not hours).
Complements `harvest-ceilings` (pagination and limit caps) and `measure-first` (where time goes).

## Five questions, each answered by a run, not a doc
1. **Does it agree with what we have?** Ask it for 3-5 known names over the last 10 days and compare with our files
   (`second-source`). Exact agreement on ordinary days is the green light; anything else is understood first.
2. **What names does it accept?** Send a long real list from our own table. One rejection reveals the mapping
   (`BRK-B`->`BRK.B`, `CON_`->`CON`) and whether one bad name kills the request (it did).
3. **Which feed/plan/adjustment?** Try each variant on one name (feed=sip vs iex, adjustment=all vs raw); compare.
4. **How big is one call?** Double the symbols and days until it refuses or slows: record symbols per call, rows per
   page, seconds per call, URL length that still works.
5. **What does an error look like?** Wrong key (401/403), bad name (400 with which name), too many (429). Save the
   bodies: the client must name the cause in words.
6. **Is there a limit the docs do not state?** Send two calls 100 ms apart with the real key (`burst_probe`). On
   2026-10-21 Alpha Vantage's page said "25 requests a day"; the second of two quick calls came back HTTP 200 with
   "Please consider spreading out your free API requests more sparingly (1 request per second)". The demo-key probe
   had sent its calls far apart and never saw it. Refusals that arrive as 200 are caught by `soft_refusal`.
7. **Is this endpoint even on our plan?** On 2026-10-24 (L11362) Alpha Vantage's NEWS_SENTIMENT and OVERVIEW both
   answered HTTP 200 with `{"Information": "...This is a premium endpoint..."}` - 215 bytes that look like a success.
   `refusal_kind(status, body)` says `premium` (drop the endpoint, never retry it, never pace for it), `rate` (slow
   down), `error` (a short `error_message` body, FRED L7207) or `""` (data). It only judges a short JSON object, so a
   CSV row naming a "Premium Income" fund stays data. Save the refusal body as a fixture too: the client test needs it.

## Spend probes from the SAME daily ledger the live job uses
A free plan's daily count is one count, shared by every caller. av_probe.py (2026-10-24) charged each probe to
`tv-screener/data/live/alphavantage_budget.json`, the file the live quote poller already counts in, and stopped at 25.
Use token-bucket's `DailyBudget(<that same path>, limit, min_gap_s=1.5)`; never a probe-only counter, or the probe
quietly eats the live job's quota. Write in the sources.toml `limits` field who shares the ledger.

## Assert the key is not in a fixture - by value, not only by shape
`scan_secrets` looks for key SHAPES and misses a plain 16-character key. Before saving a fixture also run
`key_values_in(file_bytes, {"ALPHAVANTAGE_API_KEY": key})`: it checks the raw, URL-encoded and lower-cased value and
returns names only (L11419: av_fixtures.py asserted `key not in body` for every file it wrote). The value comes from
keys-in-process `get_value()`; it is never printed. harvest-source-add's `source_add.py scan DIR --names ...` runs this
over a whole fixture folder.

## Then
- Save ONE trimmed real response under `tests/fixtures/feeds/<source>_<what>_<date>.json` (secretscan it first) and
  build the parser against it. Tests use the fixture; nothing in a test touches the network.
- Write each probe result down with its date (ledger or `UNVERIFIED.md`): limits change.
- Probe scripts live in the job's tmp folder and read keys from the environment (`keys-in-process`); keys go in
  headers only.

## The tool (ships with this skill)
```python
from probe_record import record_probe, rejected_names, trim_fixture, scan_secrets, fixture_name
rec = record_probe("alpaca", url, status, headers, body_bytes, seconds, n_names=len(symbols))
rejected_names(error_body, symbols)              # which name killed an all-or-nothing request
fixture = trim_fixture(json.loads(body_bytes), max_items=3)
assert not scan_secrets(json.dumps(fixture))     # refuse a fixture carrying a key
fixture_name("alpaca", "daily bars", "2026-10-12")  # -> alpaca_daily-bars_2026-10-12.json
rows = burst_probe(lambda: http_get(url), n=2, gap_s=0.1)   # question 6; each call still costs quota
burst_verdict(rows)   # "HIDDEN LIMIT: call 2 refused after 0.1 s (refused (soft, HTTP 200): per second)"
refusal_kind(200, body)                          # "premium" | "rate" | "error" | ""   (question 7)
key_values_in(fixture_bytes, {"NAME": value})    # ["NAME"] if the real key value is inside; names only
```
Real run 2026-10-24 over tv-harvest/tests/fixtures/alphavantage_*: six data files `''`,
`alphavantage_premium_refusal_2026-10-24.json 'premium'`.
Then pace with token-bucket's `DailyBudget(path, limit, min_gap_s=...)` (a per-day count that survives restarts).
`python probe_record.py --selftest`

Network-free: you make the call, it writes down status (cause in words: 401/403 key, 400 bad name, 429 rate), bytes,
seconds, seconds per name and the pacing/limit headers, redacts keys in the URL, and trims a real response into a
fixture that passes a secret-shape scan.
