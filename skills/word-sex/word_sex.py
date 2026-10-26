"""word_sex - breed two words into offspring words (backs the word-sex skill).

The 1-to-1 "sex" operator applied to language: two parent words cross over at vowel-group boundaries
(smoke x fog -> smog; breakfast x lunch -> brunch), and only pronounceable, novel offspring survive.
Pure stdlib, deterministic. Proof that "anything can reproduce": the parents here are words, not code.

    python word_sex.py skill sex            # ranked offspring of two words
    python word_sex.py --selftest           # 6/6; the pronounceability gate is proven able to fail
"""
from __future__ import annotations

import sys

VOWELS = set("aeiouy")


def _is_vowel(c: str) -> bool:
    return c.lower() in VOWELS


def _max_consonant_run(w: str) -> int:
    run = best = 0
    for c in w:
        if c.isalpha() and not _is_vowel(c):
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def is_pronounceable(w: str) -> bool:
    """A loose, falsifiable gate: has a vowel, no >3 consonant pile-up, sane length."""
    w = w.lower()
    if not (3 <= len(w) <= 12):
        return False
    if not any(_is_vowel(c) for c in w):
        return False
    if _max_consonant_run(w) > 3:
        return False
    return True


def _cut_points(w: str):
    """Boundaries just AFTER each vowel group - the natural seams a portmanteau crosses at."""
    pts = []
    in_vowel = False
    for i, c in enumerate(w):
        v = _is_vowel(c)
        if in_vowel and not v:          # vowel group just ended at i
            pts.append(i)
        in_vowel = v
    if in_vowel:
        pts.append(len(w))
    return pts or [len(w) // 2]


def breed(a: str, b: str, n: int = 8) -> list[tuple[str, float]]:
    """Cross parents a and b at vowel seams, both directions; return up to n pronounceable, novel
    offspring (word, score), ranked. Deterministic for fixed inputs."""
    a, b = a.strip().lower(), b.strip().lower()
    parents = {a, b}
    seen: dict[str, float] = {}
    for x, y in ((a, b), (b, a)):
        for i in _cut_points(x):
            for j in _cut_points(y):
                child = x[:i] + y[j:]
                if child in parents or not is_pronounceable(child):
                    continue
                # pivot bonus: the two halves share a letter at the seam (smoother blend)
                pivot = 1.0 if (i > 0 and j < len(y) and x[i - 1] == y[j]) else 0.0
                # naturalness: length near the average of the parents, and carries a chunk of each
                avg = (len(a) + len(b)) / 2
                length_fit = 1.0 - min(abs(len(child) - avg) / avg, 1.0)
                blends = 1.0 if (child.startswith(x[:1]) and child.endswith(y[-1:])) else 0.5
                score = round(2 * pivot + length_fit + blends, 3)
                seen[child] = max(seen.get(child, 0.0), score)
    return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _selftest() -> bool:
    ok = {}
    kids = breed("skill", "sex")
    ok["breeds >=1 offspring from skill x sex"] = len(kids) >= 1
    ok["offspring differ from both parents"] = all(w not in ("skill", "sex") for w, _ in kids)
    ok["every offspring is pronounceable"] = all(is_pronounceable(w) for w, _ in kids)
    # determinism
    ok["deterministic (same inputs -> same output)"] = (breed("skill", "sex") == kids)
    # a classic portmanteau is reachable
    smog = [w for w, _ in breed("smoke", "fog", n=20)]
    ok["reaches a real portmanteau (smog from smoke x fog)"] = ("smog" in smog)
    # the pronounceability gate actually rejects junk (this is the part that must be able to fail)
    ok["gate rejects a consonant pile-up, accepts a real word"] = (
        (not is_pronounceable("strkll")) and is_pronounceable("brunch"))
    for k, v in ok.items():
        print(("PASS " if v else "FAIL ") + k)
    if kids:
        print("  e.g. skill x sex ->", ", ".join(w for w, _ in kids[:5]))
    return all(ok.values())


def main(argv: list[str]) -> int:
    if not argv or argv[0] == "--selftest":
        return 0 if _selftest() else 1
    if len(argv) < 2:
        print("usage: word_sex.py <wordA> <wordB> [n]"); return 2
    n = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 8
    for w, s in breed(argv[0], argv[1], n):
        print(f"{w}\t{s}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
