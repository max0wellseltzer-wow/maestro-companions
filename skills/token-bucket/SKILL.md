---
name: token-bucket
description: Rate-limit calls with a token bucket (steady rate + burst capacity) or an exact sliding-window log, per endpoint or API key, with try_acquire(n), an exact wait_time(n) that never sleeps, and a blocking acquire through an injectable sleep and clock. Use this whenever the user needs to stay under an API rate ceiling ("120 requests/minute", "10 per second burst 20"), keeps getting 429s, runs a harvester/poller/downloader that must pace itself, has several endpoints or keys with separate quotas, or asks "how long until I can call again?" or "throttle this" - and for a hard COOLDOWN that debounces/throttles alerts, retries or notifications ("only let this happen once every N", minimum gap, dedup rapid repeats; refractory, with a suppressed count) or a capacity BUFFER that absorbs bursts and releases at a controlled rate with overflow accounting (backpressure, burst smoothing, "absorb a surge"). Pairs with harvest-ceilings (what the ceilings are), backoff-retry (what to do when you hit one anyway), feed-poller-add, long-job, hysteresis and capillary.
---

# token-bucket

An API that allows "N requests per window" punishes you for going over, and naive `sleep(1/rate)` loops either waste the allowed burst or drift over the limit. A token bucket gives a smooth long-run rate while letting a short burst through; a sliding-window log enforces "at most N in any trailing window" exactly (what many APIs actually count). Both answer "may I call now?" and "how long until I may?" without sleeping inside the library, so they are deterministic to test.

## The tool (ships with this skill)

`token_bucket.py` - pure stdlib, selftest 11/11:

```
from token_bucket import TokenBucket, SlidingWindowLog, MultiKeyLimiter
tb = TokenBucket(rate=2.0, burst=10)          # 2/s long run, 10 at once; starts full
if tb.try_acquire():  call()                   # non-blocking
tb.wait_time(3)                                # seconds until 3 tokens exist (0.0 if now)
tb.acquire(1)                                  # blocks via time.sleep (injectable: sleep=...)
sw = SlidingWindowLog(limit=120, window=60)    # exact "120 per rolling minute"
per = MultiKeyLimiter(lambda: TokenBucket(5, 5))
per.acquire("binance/klines"); per.acquire("polygon/aggs")   # independent quotas
python token_bucket.py --selftest
```

- `rate` (> 0, tokens/sec) and `burst` (>= 1, bucket size); guarantee: in any interval T at most `rate*T + burst` grants (brute-force checked).
- `n` per call may weigh a request (e.g. a batch costs 5); `n > burst` / `n > limit` raises ValueError because it could never be granted.
- `clock=` (default `time.monotonic`) and `acquire(sleep=..., timeout=...)` are injectable; `timeout` returns False instead of sleeping past it.
- `SlidingWindowLog` stores one timestamp per unit (memory O(limit)); `wait_time` returns when the oldest blocking unit expires.

## Daily quotas that survive restarts (added 2026-10-21)

The limiters above live in memory and start full after every restart, so they cannot hold a per-DAY quota such as
Alpha Vantage's 25 requests a day. `DailyBudget` keeps the count in a small JSON file:

```
from token_bucket import DailyBudget
budget = DailyBudget("data/live/av_budget.json", limit=25, min_gap_s=1.2)   # reset_utc_offset_h=0: UTC midnight
budget.plan(len(symbols))      # ValueError before anything is sent if the batch does not fit today
for s in symbols:
    budget.spend()             # waits out min_gap_s, counts the call BEFORE it is made, returns calls left
    get(s)
```

- `min_gap_s` exists because Alpha Vantage refused a second call inside one second (2026-10-21), a limit its quota
  page never mentions; find such limits with api-probe's `burst_probe` first.
- Spending before the request means a crash mid-request still costs one, so the count never undercounts.
- One file per key; two processes sharing a key share the file (last writer wins on a same-instant race).
- Real use: tv-screener `screener/feeds/alphavantage.py` (its own small copy, written first).

## Uses and limits

Wrap every outbound call of a harvester in `per.acquire(endpoint)` set a little under the published ceiling, and let backoff-retry handle the 429s that still happen (clock skew, shared keys, server-side counting differences). Limits: single-process and not thread-safe (put a lock around it, or one limiter per thread with a split quota); it does not coordinate across processes or machines - two jobs sharing one API key each need half the quota. The bucket starts full, so a restart can burst; pass `initial=0` to start empty.

## Hard cooldown (merged from refractory)

A neuron cannot re-fire during its refractory period. `Refractory` allows a fire, suppresses every attempt until `cooldown` has passed since the last ACCEPTED fire, then allows exactly one more - a firm max rate of one per cooldown, purely time-based.

```
from refractory import Refractory
r = Refractory(cooldown=5)
r.fire(t)        # True if allowed (and recorded), False if within the cooldown
r.suppressed     # count of blocked attempts
python refractory.py --selftest   # 6/6
```
The first event always fires. Time-based (limits how OFTEN); `hysteresis` is value-based (stops a state flip-flopping near a boundary); `apoptosis` retires after sustained failure.

## Burst buffer with overflow accounting (merged from buffer)

A bounded store absorbs bursts up to `capacity`, clips the excess as overflow, and drains at a controlled rate - conserving `stored + overflow == offered`.

```
from buffer import Buffer
b = Buffer(capacity=10)
b.absorb(amount)   # -> {stored, overflow, level}   (stored + overflow == amount)
b.drain(rate)      # -> {released, level}
python buffer.py --selftest   # 6/6
```
The overflow is the signal you exceeded capacity - log it or apply backpressure. `capillary` allocates a fixed supply across competing demands at one instant; `osmosis` equalizes across compartments.
