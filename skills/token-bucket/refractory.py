"""refractory - after an event fires, block repeats until a cooldown has passed (part of the token-bucket skill).

Fascination: the neuron's refractory period. Right after a neuron fires it CANNOT fire again for a few
milliseconds, no matter how hard it's pushed - a hard cooldown that prevents runaway re-triggering and sets a
firm maximum rate. That's the cleanest model for throttling events: allow a fire, then suppress every attempt
until the cooldown elapses, then allow one again. Distinct from a threshold band (hysteresis) - this is purely
time-since-last-event. Pure stdlib.

    from refractory import Refractory
    python refractory.py --selftest   # 6/6; a fire within the cooldown is suppressed; after it, allowed again
"""
from __future__ import annotations

import sys


class Refractory:
    """Event throttle with a hard cooldown. fire(t) returns True and records the event if at least `cooldown`
    has passed since the last accepted fire; otherwise returns False and counts the suppression."""

    def __init__(self, cooldown: float):
        self.cooldown = cooldown
        self.last = None
        self.suppressed = 0

    def fire(self, t: float) -> bool:
        if self.last is None or t - self.last >= self.cooldown:
            self.last = t
            return True
        self.suppressed += 1
        return False


def _selftest() -> bool:
    ok = {}
    r = Refractory(cooldown=5)
    ok["the first event always fires"] = (r.fire(0) is True)
    ok["an event within the cooldown is suppressed"] = (r.fire(3) is False)
    ok["another within the cooldown is also suppressed"] = (r.fire(4) is False)
    ok["an event exactly at the cooldown fires"] = (r.fire(5) is True)          # 5 - 0 >= 5
    ok["an event within the NEW cooldown is suppressed"] = (r.fire(9) is False)  # 9 - 5 < 5
    ok["suppressed attempts are counted"] = (r.suppressed == 3)
    # it enforces a max average rate (one fire per cooldown)
    r2 = Refractory(cooldown=10)
    fires = sum(1 for t in range(0, 100) if r2.fire(t))   # 100 ticks, cooldown 10
    ok["it caps the rate (~1 per cooldown over the window)"] = (fires == 10)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print("refractory is a library: from refractory import Refractory")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
