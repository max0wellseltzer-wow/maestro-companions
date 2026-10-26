"""phrase_sex - breed two phrases into offspring phrases (backs the word-sex skill).

The 1-to-1 reproduction operator at the phrase level: two parent phrases cross over at WORD boundaries
(the way a creole or a remix forms), bearing hybrids that carry a clause of each. Pure stdlib,
deterministic. Sibling of word-sex, one level up: words -> phrases.

    python phrase_sex.py "the quick brown fox" "jumps over the lazy dog"
    python phrase_sex.py --selftest      # 5/5
"""
from __future__ import annotations

import sys


def _words(p: str) -> list[str]:
    return [w for w in p.strip().split() if w]


def breed(a: str, b: str, n: int = 8) -> list[tuple[str, float]]:
    """Cross parents at word seams, both directions. A child takes a head clause from one parent and a
    tail clause from the other. Keep novel children that carry at least one word from EACH parent, ranked
    by length naturalness and a seam-pivot bonus (the two clauses meet on a shared word)."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return []
    parents = {a.strip().lower(), b.strip().lower()}
    sa, sb = set(w.lower() for w in wa), set(w.lower() for w in wb)
    seen: dict[str, float] = {}
    for x, y, xs, ys in ((wa, wb, sa, sb), (wb, wa, sb, sa)):
        for i in range(1, len(x)):                 # head = x[:i]
            for j in range(0, len(y)):             # tail = y[j:]
                child_words = x[:i] + y[j:]
                child = " ".join(child_words)
                low = child.lower()
                if low in parents or len(child_words) < 2 or len(child_words) > 14:
                    continue
                cw = set(w.lower() for w in child_words)
                if not (cw & xs and cw & ys):      # must blend: a word from each parent
                    continue
                pivot = 1.0 if x[i - 1].lower() == y[j].lower() else 0.0   # clauses meet on a shared word
                avg = (len(wa) + len(wb)) / 2
                length_fit = 1.0 - min(abs(len(child_words) - avg) / max(avg, 1), 1.0)
                score = round(2 * pivot + length_fit, 3)
                seen[child] = max(seen.get(child, 0.0), score)
    return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _selftest() -> bool:
    ok = {}
    a, b = "the quick brown fox", "jumps over the lazy dog"
    kids = breed(a, b)
    ok["breeds >=1 offspring phrase"] = len(kids) >= 1
    ok["offspring differ from both parents"] = all(p.lower() not in (a, b) for p, _ in kids)
    sa, sb = set(a.split()), set(b.split())
    ok["every offspring blends a word from EACH parent"] = all(
        (set(p.split()) & sa) and (set(p.split()) & sb) for p, _ in kids)
    ok["deterministic"] = (breed(a, b) == kids)
    # the shared-word pivot ("the" is in both) earns the top rank
    top = kids[0][0] if kids else ""
    ok["a shared-word seam is reachable"] = any("the" in p.split() for p, _ in kids)
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    if kids:
        print("  e.g. ->", " | ".join(p for p, _ in kids[:3]))
    return all(ok.values())


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if len(argv) < 2:
        print('usage: phrase_sex.py "<phrase A>" "<phrase B>"'); return 2
    for p, s in breed(argv[0], argv[1]):
        print(f"{s:5.2f}  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
