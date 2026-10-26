"""epigenetic_switch - change behavior without changing the genome, heritably (backs epigenetic-switch).

Reproduction here is epigenetics: the DNA (the base config) is untouched, but environmental MARKS switch genes
on and off, and those marks are inherited by the next generation. Apply it to configuration: keep a frozen
base ('genome') and a separate overlay of marks that the environment sets; behavior reads base+marks, the base
is never mutated, and a child inherits the parent's marks. Clearing the marks reverts exactly to the genome.
Pure stdlib.

    from epigenetic_switch import effective, set_mark, inherit, clear_marks
    python epigenetic_switch.py --selftest   # 6/6; the base is proven never to mutate; marks are heritable
"""
from __future__ import annotations

import sys


def effective(base: dict, marks: dict) -> dict:
    """The expressed config = base overlaid by marks. Marks win where present; the base is read-only here."""
    out = dict(base)
    out.update(marks)
    return out


def set_mark(marks: dict, key: str, value) -> dict:
    """Return a NEW marks overlay with key switched - never mutate the passed-in marks (so history is clean)."""
    m = dict(marks)
    m[key] = value
    return m


def inherit(marks: dict) -> dict:
    """A child inherits the parent's epigenetic marks (a copy it can then diverge from)."""
    return dict(marks)


def clear_marks() -> dict:
    """Erase all marks - expression reverts exactly to the base genome."""
    return {}


def _selftest() -> bool:
    ok = {}
    base = {"mode": "paper", "risk": "off", "size": 0}      # the genome
    base_snapshot = dict(base)
    marks = {}
    ok["with no marks, expression == genome"] = (effective(base, marks) == base)
    marks = set_mark(marks, "risk", "on")
    ok["a mark switches behavior"] = (effective(base, marks)["risk"] == "on")
    ok["the base genome is NOT mutated by marking"] = (base == base_snapshot)
    child = inherit(marks)
    child = set_mark(child, "size", 10)
    ok["a child inherits parent marks and can diverge"] = (
        effective(base, child)["risk"] == "on" and effective(base, child)["size"] == 10
        and "size" not in marks)                             # parent not retro-changed
    ok["clearing marks reverts to the genome"] = (effective(base, clear_marks()) == base)
    # a mark can never silently change a key the genome doesn't have into the genome itself
    m2 = set_mark({}, "newflag", True)
    ok["marks overlay without editing the genome keys"] = (
        "newflag" not in base and effective(base, m2)["newflag"] is True)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    return all(ok.values())


def main(argv):
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    print("epigenetic_switch is a library: from epigenetic_switch import effective, set_mark, inherit, clear_marks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
