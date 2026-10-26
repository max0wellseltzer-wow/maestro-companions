"""token_bucket.py - rate limiters for staying under API ceilings (pure stdlib).

TokenBucket(rate, burst)        - refills `rate` tokens/sec up to `burst`; starts full.
SlidingWindowLog(limit, window) - at most `limit` units in any trailing `window` seconds (exact).
MultiKeyLimiter(factory)        - one independent limiter per key (endpoint, API key, host).

Every limiter has try_acquire(n) -> bool (non-blocking), wait_time(n) -> seconds until
n units would be granted (never sleeps), and acquire(n, sleep=..., timeout=...) which
blocks through an injectable sleep. The clock is injectable too (default time.monotonic).

    python token_bucket.py --selftest
"""
import collections
import random
import sys
import time

_EPS = 1e-9  # float slack so a sleep of exactly wait_time() always succeeds


def _check_n(n, cap, what):
    if not isinstance(n, (int, float)) or n <= 0:
        raise ValueError(f"n must be > 0, got {n!r}")
    if n > cap:
        raise ValueError(f"n={n} exceeds {what}={cap}; it could never be granted")


class TokenBucket:
    """Token bucket: long-run rate `rate`/sec, bursts up to `burst` tokens."""

    def __init__(self, rate, burst, clock=time.monotonic, initial=None):
        if not rate or rate <= 0:
            raise ValueError(f"rate must be > 0, got {rate!r}")
        if burst is None or burst < 1:
            raise ValueError(f"burst must be >= 1, got {burst!r}")
        self.rate = float(rate)
        self.burst = float(burst)
        self.clock = clock
        self._tokens = self.burst if initial is None else min(float(initial), self.burst)
        self._last = clock()

    def _refill(self):
        now = self.clock()
        if now > self._last:
            self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
            self._last = now
        return now

    @property
    def tokens(self):
        self._refill()
        return self._tokens

    def try_acquire(self, n=1):
        _check_n(n, self.burst, "burst")
        self._refill()
        if self._tokens + _EPS >= n:
            self._tokens = max(0.0, self._tokens - n)
            return True
        return False

    def wait_time(self, n=1):
        _check_n(n, self.burst, "burst")
        self._refill()
        deficit = n - self._tokens
        return 0.0 if deficit <= _EPS else deficit / self.rate

    def acquire(self, n=1, sleep=time.sleep, timeout=None):
        return _blocking_acquire(self, n, sleep, timeout)


class SlidingWindowLog:
    """Exact sliding window: grants n only if units granted in (now-window, now] plus n <= limit."""

    def __init__(self, limit, window, clock=time.monotonic):
        if limit is None or limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit!r}")
        if not window or window <= 0:
            raise ValueError(f"window must be > 0, got {window!r}")
        self.limit = int(limit)
        self.window = float(window)
        self.clock = clock
        self._log = collections.deque()  # timestamps, one per unit granted

    def _evict(self):
        now = self.clock()
        cutoff = now - self.window
        log = self._log
        while log and log[0] <= cutoff:
            log.popleft()
        return now

    def in_window(self):
        self._evict()
        return len(self._log)

    def try_acquire(self, n=1):
        _check_n(n, self.limit, "limit")
        now = self._evict()
        if len(self._log) + n <= self.limit:
            self._log.extend([now] * int(n))
            return True
        return False

    def wait_time(self, n=1):
        _check_n(n, self.limit, "limit")
        now = self._evict()
        excess = len(self._log) + int(n) - self.limit
        if excess <= 0:
            return 0.0
        # the `excess`-th oldest entry must expire; it leaves at ts + window
        return max(0.0, self._log[excess - 1] + self.window - now)

    def acquire(self, n=1, sleep=time.sleep, timeout=None):
        return _blocking_acquire(self, n, sleep, timeout)


def _blocking_acquire(lim, n, sleep, timeout):
    """Sleep (injectable) until granted. Returns True, or False if timeout would be exceeded."""
    waited = 0.0
    while True:
        if lim.try_acquire(n):
            return True
        w = lim.wait_time(n)
        if w <= 0:
            w = _EPS  # float edge: nudge forward rather than spin
        if timeout is not None and waited + w > timeout + _EPS:
            return False
        sleep(w)
        waited += w


class MultiKeyLimiter:
    """Independent limiter per key. factory() -> fresh limiter (e.g. lambda: TokenBucket(5, 10))."""

    def __init__(self, factory):
        self.factory = factory
        self._lims = {}

    def get(self, key):
        lim = self._lims.get(key)
        if lim is None:
            lim = self._lims[key] = self.factory()
        return lim

    def try_acquire(self, key, n=1):
        return self.get(key).try_acquire(n)

    def wait_time(self, key, n=1):
        return self.get(key).wait_time(n)

    def acquire(self, key, n=1, sleep=time.sleep, timeout=None):
        return self.get(key).acquire(n, sleep=sleep, timeout=timeout)

    def keys(self):
        return list(self._lims)


class DailyBudget:
    """A per-day request quota that survives restarts, plus a minimum gap between calls.

    The free plans that cap calls per DAY (Alpha Vantage 25/day, NewsAPI 100/day) need a count that outlives the
    process: the in-memory limiters above start full after every restart. The count lives in a small JSON file
    {"2026-10-21": 3, ...}, rewritten atomically. `reset_utc_offset_h` sets where the day boundary falls (0 = UTC
    midnight). `min_gap_s` spaces calls: Alpha Vantage refused a second call inside one second (seen 2026-10-21),
    a limit the quota page never mentions. Spend BEFORE the request: a crash mid-request still costs one.
    """

    def __init__(self, path, limit, min_gap_s=0.0, reset_utc_offset_h=0.0, clock=time.time):
        import pathlib
        _check_n(limit, float("inf"), "limit")
        self.path, self.limit, self.min_gap_s = pathlib.Path(path), int(limit), float(min_gap_s)
        self.offset_s, self.clock, self._last = reset_utc_offset_h * 3600.0, clock, None

    def _day(self, t):
        return time.strftime("%Y-%m-%d", time.gmtime(t + self.offset_s))

    def _load(self):
        import json
        try:
            return dict(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}

    def left(self):
        return self.limit - self._load().get(self._day(self.clock()), 0)

    def plan(self, n):
        """Raise ValueError before anything is sent when n calls do not fit in what is left today."""
        if n > self.left():
            raise ValueError(f"{n} calls but only {self.left()} of {self.limit} left today")

    def spend(self, sleep=time.sleep):
        """Wait out min_gap_s since the last spend, then count one call. Returns calls left today."""
        import json
        import os
        if self._last is not None and self.min_gap_s:
            gap = self._last + self.min_gap_s - self.clock()
            if gap > 0:
                sleep(gap)
        now = self.clock()
        book = self._load()
        day = self._day(now)
        if book.get(day, 0) >= self.limit:
            raise ValueError(f"daily budget {self.limit} spent for {day}")
        book[day] = book.get(day, 0) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(book, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.path)
        self._last = now
        return self.limit - book[day]


# ---------------------------------------------------------------- selftest

class _FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


def _selftest():
    ok_all = True

    def report(name, ok, detail):
        nonlocal ok_all
        ok_all &= bool(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}: {detail}")

    rng = random.Random(20261015)

    # 1. never exceeds rate*T + burst over any window (brute force over all granted pairs)
    worst = -1e9
    grants_total = 0
    for trial in range(5):
        rate, burst = rng.choice([(2.0, 5), (10.0, 1), (0.5, 3), (7.0, 20)])
        ck = _FakeClock()
        tb = TokenBucket(rate, burst, clock=ck)
        times = sorted(rng.uniform(0, 60) for _ in range(600))
        granted = []
        for t in times:
            ck.t = t
            if tb.try_acquire(1):
                granted.append(t)
        grants_total += len(granted)
        for i in range(len(granted)):
            for j in range(i, len(granted)):
                slack = (j - i + 1) - (rate * (granted[j] - granted[i]) + burst)
                worst = max(worst, slack)
    report("never_exceeds_rate_T_plus_burst", worst <= 1e-6,
           f"{grants_total} grants / 5 trials, max(count - (rate*T+burst)) = {worst:.3g} (must be <= 0)")

    # 2. burst allowed up front, then denied
    ck = _FakeClock()
    tb = TokenBucket(rate=1.0, burst=8, clock=ck)
    got = sum(tb.try_acquire(1) for _ in range(8))
    ninth = tb.try_acquire(1)
    report("burst_up_front", got == 8 and not ninth, f"{got}/8 granted at t=0, 9th granted={ninth}")

    # 3. wait_time exact, and sleeping exactly that long succeeds
    ck = _FakeClock()
    tb = TokenBucket(rate=2.0, burst=5, clock=ck)
    for _ in range(5):
        tb.try_acquire(1)
    w1, w3 = tb.wait_time(1), tb.wait_time(3)
    ck.sleep(w1)
    a = tb.try_acquire(1)
    b = tb.try_acquire(1)
    ck.t = 10.0  # full refill, capped at burst
    w0 = tb.wait_time(5)
    ok = abs(w1 - 0.5) < 1e-12 and abs(w3 - 1.5) < 1e-12 and a and not b and w0 == 0.0
    report("wait_time_exact", ok, f"wait(1)={w1} (0.5), wait(3)={w3} (1.5), after sleep granted={a}, "
           f"next={b}, refilled wait(5)={w0}")

    # 4. blocking acquire uses injected sleep: 10 units at rate 1, burst 2 -> 8 s slept
    ck = _FakeClock()
    tb = TokenBucket(rate=1.0, burst=2, clock=ck)
    for _ in range(10):
        tb.acquire(1, sleep=ck.sleep)
    to = TokenBucket(rate=1.0, burst=2, clock=ck)
    to.try_acquire(2)
    timed_out = to.acquire(2, sleep=ck.sleep, timeout=1.0)
    report("blocking_acquire_fake_sleep", abs(ck.t - 8.0) < 1e-6 and timed_out is False,
           f"slept {ck.t:.6f}s for 10 units (expect 8.0); timeout=1s on 2s wait -> {timed_out}")

    # 5. sliding window log matches brute-force decision on random requests (incl. n>1)
    mism = 0
    total = 0
    waits_bad = 0
    for limit, window in [(5, 1.0), (1, 0.3), (20, 10.0)]:
        ck = _FakeClock()
        sw = SlidingWindowLog(limit, window, clock=ck)
        accepted = []  # (time, n)
        for t in sorted(rng.uniform(0, 50) for _ in range(800)):
            ck.t = t
            n = rng.choice([1, 1, 1, 2]) if limit >= 2 else 1
            used = sum(k for (s, k) in accepted if s > t - window)
            want = used + n <= limit
            w = sw.wait_time(n)
            if (w == 0.0) != want:
                waits_bad += 1
            got = sw.try_acquire(n)
            total += 1
            if got != want:
                mism += 1
            if got:
                accepted.append((t, n))
            elif w > 0:
                # brute force: just after t+w the request fits, just before it does not
                # (+-1e-7 probes: at exactly t+w, at-window can round 1 ulp either way)
                def fits(at):
                    return sum(k for (s, k) in accepted if s > at - window) + n <= limit
                if not fits(t + w + 1e-7) or fits(t + w - 1e-7):
                    waits_bad += 1
    report("sliding_window_matches_bruteforce", mism == 0 and waits_bad == 0,
           f"{total} requests, {mism} decision mismatches, {waits_bad} wait_time mismatches")

    # 6. per-key isolation
    ck = _FakeClock()
    mk = MultiKeyLimiter(lambda: TokenBucket(rate=1.0, burst=3, clock=ck))
    a = sum(mk.try_acquire("endpointA") for _ in range(5))
    b = sum(mk.try_acquire("endpointB") for _ in range(5))
    wa, wb = mk.wait_time("endpointA"), mk.wait_time("endpointC")
    report("per_key_isolation", a == 3 and b == 3 and wa > 0 and wb == 0.0,
           f"A granted {a}/5, B granted {b}/5 (each 3), wait A={wa}, fresh C wait={wb}")

    # 7. planted bad inputs rejected
    bad = [
        ("rate=0", lambda: TokenBucket(0, 5)),
        ("rate=-1", lambda: TokenBucket(-1, 5)),
        ("burst=0", lambda: TokenBucket(1, 0)),
        ("burst=0.5", lambda: TokenBucket(1, 0.5)),
        ("n>burst", lambda: TokenBucket(1, 3, clock=_FakeClock()).try_acquire(4)),
        ("wait n>burst", lambda: TokenBucket(1, 3, clock=_FakeClock()).wait_time(4)),
        ("n=0", lambda: TokenBucket(1, 3, clock=_FakeClock()).try_acquire(0)),
        ("window=0", lambda: SlidingWindowLog(5, 0)),
        ("limit=0", lambda: SlidingWindowLog(0, 1)),
        ("n>limit", lambda: SlidingWindowLog(2, 1, clock=_FakeClock()).try_acquire(3)),
    ]
    caught = []
    for name, fn in bad:
        try:
            fn()
        except ValueError:
            caught.append(name)
    report("bad_inputs_rejected", len(caught) == len(bad),
           f"{len(caught)}/{len(bad)} planted bad inputs raised ValueError")

    # 8. long-run rate: saturating client over 100 s gets ~rate*100 + burst
    ck = _FakeClock()
    tb = TokenBucket(rate=3.0, burst=4, clock=ck)
    n = 0
    while ck.t < 100.0:
        tb.acquire(1, sleep=ck.sleep)
        n += 1
    report("long_run_rate", abs(n - (3.0 * 100 + 4)) <= 1, f"{n} grants in 100 s (expect ~304)")

    # 9. DailyBudget: survives a restart, refuses past the limit, a new day starts fresh
    import calendar
    import tempfile
    import pathlib
    t0 = float(calendar.timegm((2026, 10, 21, 0, 0, 0)))   # computed, not typed
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "budget.json"
        ck = _FakeClock(t0)                                # 2026-10-21 00:00 UTC
        a = DailyBudget(p, 3, clock=ck)
        a.spend(sleep=ck.sleep)
        a.spend(sleep=ck.sleep)
        b = DailyBudget(p, 3, clock=ck)                    # a second process reads the same ledger
        left_b = b.left()
        b.spend(sleep=ck.sleep)
        try:
            b.spend(sleep=ck.sleep)
            over = False
        except ValueError:
            over = True
        try:
            b.plan(1)
            planned = False
        except ValueError:
            planned = True
        ck.t += 86400
        report("daily_budget_persists_and_resets", left_b == 1 and over and planned and b.left() == 3,
               f"left after restart {left_b} (expect 1), over-limit refused {over}, plan refused {planned}, "
               f"next day {b.left()}")

        # 10. min_gap_s: the second call waits out the gap through the injected sleep
        waits = []
        ck2 = _FakeClock(t0)

        def rec(dt):
            waits.append(dt)
            ck2.sleep(dt)
        g = DailyBudget(pathlib.Path(td) / "g.json", 25, min_gap_s=1.2, clock=ck2)
        g.spend(sleep=rec)
        ck2.t += 0.3
        g.spend(sleep=rec)
        report("daily_budget_min_gap", len(waits) == 1 and abs(waits[0] - 0.9) < 1e-6,
               f"waits {waits} (expect [0.9])")

        # 11. the day boundary follows reset_utc_offset_h (New York evening is the next UTC day)
        ck3 = _FakeClock(t0 + 23.5 * 3600)        # 2026-10-21 23:30 UTC
        utc = DailyBudget(pathlib.Path(td) / "u.json", 5, clock=ck3)
        ny = DailyBudget(pathlib.Path(td) / "u.json", 5, reset_utc_offset_h=-4, clock=ck3)
        report("daily_budget_offset", utc._day(ck3()) == "2026-10-21" and ny._day(ck3()) == "2026-10-21"
               and utc._day(ck3() + 3600) == "2026-10-22" and ny._day(ck3() + 3600) == "2026-10-21",
               "UTC rolls at 00:00 UTC, offset -4 rolls at 04:00 UTC")

    return ok_all


def main(argv):
    if not argv or "--selftest" in argv:
        return 0 if _selftest() else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
