---
name: demand-scan
description: Route every REAL the user prompt from the transcripts through skill-finder and count, per skill, how many actual asks it would have served (demand), which skills no real ask ever needed (zero demand - retirement candidates for skill-retire, never auto-deleted) and which asks no skill serves well (weak best score - gaps for skill-foundry). Use this whenever the user asks which skills actually get used or needed, which skills to retire or merge, what needs are still uncovered, or after a big batch of new skills to see whether they meet real demand. Pairs with skill-finder, prompt-genealogy, route-audit, skill-retire and skill-foundry.
---

# demand-scan

This reverses **skill-finder**. skill-finder starts from a need and finds a skill. demand-scan starts from each skill and asks which of the user's real prompts actually needed it.

It is a fairer routing test than **route-audit**. route-audit feeds the router each skill's own story-style pitch, written by the same hand that wrote the skill. demand-scan feeds it what the user actually typed, with his spelling, his shorthand and his mixed asks.

## The tool (ships with this skill)

`demand_scan.py` uses only the standard library plus two sibling skills: prompt-genealogy's `iter_prompts` reads the prompts, and skill-finder's `search` routes them. Its selftest has 8 checks on a synthetic transcript and library.

```
python demand_scan.py                         # real library x every real the user prompt (~1 min)
python demand_scan.py --top 3 --weak 8 --show 15 [transcripts...]
python demand_scan.py --json > demand.json
from demand_scan import scan, render
```

- **demand**: `hits` counts the asks where the skill was in the top-k. `top1` counts the asks where it ranked first.
- **zero demand**: skills that no real ask routed to. These are CANDIDATES for skill-retire. Read each one before retiring it, because a sound but rarely needed tool, such as a statistics primitive another skill imports, can show zero here. This tool never deletes anything.
- **unserved**: asks whose best score is below `--weak`. Many are conversational ("yes complete all penwork"). The ones that name a real need are gaps for skill-foundry.
- Prompts with fewer than 4 routable words ("go", "MORE") are not asks and are skipped. Each prompt is cut to its first 1,500 characters, so a pasted wall of text does not match everything.

## Uses and limits

- Demand is measured against the router, not against use. A skill the user invokes by name, or one Claude loads on its own, can still show zero. Combine this with skill-retire's own evidence.
- The `--weak` bar is absolute and depends on library size, because TF-IDF scores grow with the number of skills. Re-read the unserved list rather than trusting a count.
- First run (2026-10-16): 415 real asks and 139 non-asks. About 100 of roughly 300 skills had zero demand, mostly statistics and nature-metaphor tools that the user reaches through other skills. Top demand went to finish-everything, night-shift-tripwire, restriction-matrix, writer-pen and lace-cycle.
