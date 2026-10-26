---
name: lane-resurrection
description: Ask which DEAD trading-lane verdicts have gone STALE - read every lane whose standing verdict is DEAD (through dead-lane-check's lane_verdict reader, source lines included), pull out what each verdict depended on (data end date, sample size or power, the null or test used, a named bug or erratum), compare that with what has changed since (newer data, nulls that self-attacking-referee's null_audit_sweep flags as flawed, fixed errata), and return STILL DEAD or RE-JUDGE with the changed input and the reproduce-before-rejudge step to run first. Use this whenever the user asks whether a killed idea deserves another look, what has changed since a lane died, after an erratum or a null fix lands, after new data arrives, or when reviewing GRAVEYARD.md. Pairs with dead-lane-check, reproduce-before-rejudge, self-attacking-referee, pre-register and research-spine.
---

# lane-resurrection

Reverses **dead-lane-check**. Angle flip: dead-lane-check looks forward from a new idea and refuses to re-run a lane the record calls DEAD; lane-resurrection starts from the verdicts themselves and asks which DEAD calls rested on inputs that have since changed.

A verdict is only as good as what went into it. The 2026-10-10 stock scan's p=0.080 came from a per-stock null that self-attacking-referee later showed calls luck an edge on clustered days (E77/E81). Any lane killed or kept alive by that null was judged with a broken instrument. The same is true of a lane killed on data that ends before newer bars arrived, or on code that carried a since-fixed bug. dead-lane-check, by design, will never raise those cases.

1. Run the tool over the same record dead-lane-check reads (the memory folder, GRAVEYARD.md, receipts). Give it what has changed: data dates (`--data "LTC=2026-10-12"`, or `--data-dir`), flawed nulls (`--flawed-null`, or `--null-code <repo>` so null_audit_sweep's `find` lists PER_ITEM_DRAW nulls), and fixed errata (`--fixed-erratum E77`, or `--errata <file>`).
2. For a **RE-JUDGE** lane, do the step first: reproduce the DEAD result like-for-like with reproduce-before-rejudge (the original method, the original data end, expecting the saved numbers). Only if it reproduces, change the ONE input that changed. Pre-register the re-judge, and pass the same sentence to dead-lane-check as `--different "..."`.
3. **STILL DEAD** stays dead. Read the "depended on" line anyway: `nulls unnamed (p-value given)` means the line does not say which null produced its p-value, so open its receipt before trusting it.

## The tool (ships with this skill)

`resurrect.py` is pure stdlib plus dead-lane-check's `lane_verdict` and, optionally, self-attacking-referee's `null_audit_sweep.find`. Its selftest runs 10 checks on synthetic verdict files, including a planted malformed date.

```
python resurrect.py --record <memory dir> --record <GRAVEYARD.md> --record <receipts> \
    --flawed-null per_stock_scatter --flawed-null random_timing --data "LTC=2026-10-12" [--lane "R1 RSI"] [--json]
python resurrect.py --selftest       # exit 0 nothing to re-judge, 1 at least one RE-JUDGE, 2 bad args
from resurrect import judge, discover, depends
```

Without `--lane`, lanes are discovered from DEAD lines in the record's .md files: a table row's first cell, or the text before ": " in a bullet. Each lane is then looked up with lane_verdict, and only lanes whose STANDING verdict is DEAD are judged.

## Uses and limits

- Discovery is heuristic. On the real record it also surfaces lines that are not lanes (receipt prose such as "stale copy"), so read the lane names and pass `--lane` for the ones you mean.
- The data end is read only from "through/to/until <date>" in the verdict line. Otherwise it is ASSUMED to be the verdict's date, and the output says "(assumed)". A RE-JUDGE that rests on an assumed data end is a prompt to check the receipt's real data range, not a finding.
- A flawed null counts only when the verdict line names it. Most lines give only a p-value, and those show `nulls unnamed`.
- It reads only and changes no verdict. Writing a lane back to OPEN is a person's call, after the reproduce step and the re-judge have run.
