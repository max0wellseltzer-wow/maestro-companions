---
name: pov-core
description: The shared engine of the point-of-view family - loads any subject (text, series, table, code, plan, items), gives every lens the same text and series helpers, the one view record they all return, a shared probe corpus, and a distinctness check that proves two lenses actually see differently rather than being renamed twins. Use this whenever building, running, comparing or ratifying a point-of-view lens skill, or when the user asks how many ways there are to look at something. Pairs with lens-carousel, council-of-views, lens-coverage, skill-foundry and skill-health.
---

# pov-core

the user asked for a family of at least 200 skills that cycle, mutate, obliterate, focus, distort and change the shape of a view, and that also work around it (the subconscious, the senses, the crowd). Each member of the family is a **lens**: `apply(subject, kind=None, **opts) -> view`. This folder holds what the lenses share, so each lens file contains only its own operation.

## The tool (ships with this skill)

`pov_core.py` - pure stdlib, selftest 7/7.

```
from pov_core import load_subject, sentences, words, keywords, numbers_with_units
from pov_core import mean, sd, median, mad, quantile, diff, moving_average, ranks, zscores, corr, code_functions
from pov_core import view, render, PROBES, fingerprint, distinctness, run_cli, report
```

- **Subjects.** A subject is one of six kinds: `text`, `series`, `table`, `code`, `plan` or `items`. `load_subject` reads a file path or literal text and detects the kind. `--kind` forces it.
- **The view record.** Every lens returns `view(name, kind, findings, summary, **stats)`, where findings is a list of dicts that each carry a `what` line.
- **Ratification.** Each lens selftests on `PROBES`. `distinctness({lens: view})` flags any two lenses whose output on the same probe overlaps by 0.8 or more on token-shingle Jaccard. That is the proof that a lens is not a renamed twin.

`ratify.py` is the family's ratification gate (selftest 6/6). It finds the members itself: every skill whose tool imports pov_core and defines `apply()`. It then checks each member against four rules:

- **R1:** it is a member.
- **R2:** its selftest exits 0 with at least 6 PASS, no FAIL, and a planted case.
- **R3:** skill-health reports 0 FAIL / 0 WARN.
- **R4:** it is distinct from every sibling on each shared probe.

Results are appended to `RATIFIED.jsonl`. `--max a,b` then records the user's own sign-off, and only on lenses the machine already ratified.

```
python ratify.py --all      # the whole family -> table of anything NOT ratified + counts
python ratify.py --max microscope,squint
```

## Uses and limits

- Lenses change how something is seen. They do not decide what is true. A lens finding is a question worth asking, not a verdict.
- The text helpers are heuristic: regex sentences, a fixed stopword list, and units from a short list.
- Series helpers are fine for thousands of points. They are not numpy.
