"""buffer - absorb bursts up to a capacity and release smoothly; overflow the rest (part of the token-bucket skill).

Fascination: a chemical buffer (and a reservoir, a capacitor, a shock absorber). A pH buffer soaks up added acid
without the pH lurching - up to its capacity, past which it gives way. The same shape is a leaky/token bucket:
a store absorbs incoming bursts up to a capacity (clipping the excess as overflow) and drains at a controlled
rate, turning spiky input into bounded, smooth output. It's the primitive behind rate limiting, backpressure,
and smoothing. Pure stdlib.

    from buffer import Buffer
    python buffer.py --selftest   # 6/6; within capacity is absorbed; a burst overflows; drain releases
"""
from __future__ import annotations

import sys


class Buffer:
    """A bounded reservoir. absorb(amount) stores up to the remaining capacity and reports the overflow;
    drain(rate) releases up to `rate` from the current level. Conserves: stored + overflow == amount."""

    def __init__(self, capacity: float):
        self.capacity = capacity
        self.level = 0.0
        self.total_overflow = 0.0

    def absorb(self, amount: float) -> dict:
        space = self.capacity - self.level
        stored = min(amount, space)
        overflow = amount - stored
        self.level += stored
        self.total_overflow += overflow
        return {"stored": stored, "overflow": overflow, "level": self.level}

    def drain(self, rate: float) -> dict:
        released = min(rate, self.level)
        self.level -= released
        return {"released": released, "level": self.level}


def _selftest() -> bool:
    ok = {}
    b = Buffer(10)
    r1 = b.absorb(6)
    ok["absorbs within capacity, no overflow"] = (r1["stored"] == 6 and r1["overflow"] == 0 and r1["level"] == 6)
    r2 = b.absorb(8)
    ok["a burst beyond capacity overflows the excess"] = (r2["stored"] == 4 and r2["overflow"] == 4 and r2["level"] == 10)
    ok["stored + overflow == the amount offered (conserved)"] = (r2["stored"] + r2["overflow"] == 8)
    r3 = b.drain(3)
    ok["drain releases from the level"] = (r3["released"] == 3 and r3["level"] == 7)
    # draining more than present releases only what's there
    r4 = b.drain(100)
    ok["drain cannot release more than is stored"] = (r4["released"] == 7 and r4["level"] == 0)
    # a full buffer clips a burst to its capacity (shock absorbed)
    c = Buffer(5)
    c.absorb(100)
    ok["a full buffer clips the burst to capacity"] = (c.level == 5 and c.total_overflow == 95)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print("buffer is a library: from buffer import Buffer")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
