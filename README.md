# maestro-companions (Claude Code plugin package, v0.1.0)

Sixty-seven skills that go well with skill-maestro, chosen by evidence, not by theme: every skill the Maestro's own ledger shows was read, tried, judged to fit or rated useful in real sessions on the author's machine (pack_build.py --suggest, 2026-10-26), plus pov-core, the engine the twenty-two point-of-view lenses run on, and literal-execution, which finish-everything loads. Each skill folder keeps its SKILL.md and scripts; paths and the author's name are scrubbed. Some were written for one workspace's rituals (landing, decisions, scheduled tasks); their SKILL.md says so in its first lines.

## Install

```
/plugin marketplace add max0wellseltzer-wow/maestro-companions
/plugin install maestro-companions@maestro-companions
```

By hand: copy every folder under `skills/` into `~/.claude/skills/`.

## Skills (67)

| skill | what it is for |
|---|---|
| `pov-core` | The shared engine of the point-of-view family - loads any subject (text, series, table, code, plan, items), gives every lens the same text and series helpers... |
| `falsifier-view` | Writes for each claim the concrete observation that would refute it (counterexample, missed date, value out of range, effect without cause) and flags the cla... |
| `inner-critic` | Writes the harshest specific critique question for each claim in a text, aimed at its weakest spot such as an unsourced number, an absolute word or a causal... |
| `additions-only-splice` | Add a section to a large file (a 1.5 MB plan, DECISIONS, a memory file) without changing one existing line - insert a block before or after a marker that mus... |
| `api-probe` | Before building on any outside API, spend five minutes probing it for real - name mapping, all-or-nothing rejections, feed/plan differences, premium endpoint... |
| `decision-renumber` | How to land branches that each drafted their own DECISIONS.md numbers without editing a row on main, losing a row, or using a number twice - order-only confl... |
| `land-a-change` | Land a code change in this workspace with the exact ritual - tests, lint, tests.json registry, check_all.bat until it ends CHECK_ALL PASSED, submodule commit... |
| `worms-eye` | Start from the lowest step of a plan or the leaf functions of code and list upward what each bottom step must assume about everything above it. |
| `devils-advocate` | Finds each conclusion sentence, classifies it (causal, numeric, absolute, forecast, recommendation) and writes a counter-argument from a template filled with... |
| `doc-truth` | Check that every command a doc shows still matches its script - for each `python X.py ...` invocation in a SKILL.md, README or plan (code blocks, inline back... |
| `dream-recombination` | A seeded "dream pass" over many past documents (transcripts, notes, prompt archives, findings files) - keep each document's most salient terms by TF-IDF, dra... |
| `exaptation-finder` | The skill library's function index - walks every tool .py with ast, records each public top-level function (skill, file, args with defaults, docstring line,... |
| `finish-everything` | Never quit early and never stop with an ask unfinished - before the final reply, list every ask and question in the user's prompt (via literal-execution), at... |
| `future-self` | Lists a plan's irreversible steps (delete, push, publish, send, drop, overwrite) and deferred costs (later, TODO, temporary, skip) and phrases them as next-w... |
| `hostile-caller-pass` | Read an API with grants, authors, ids, evidence or person-only doors the way a caller who wants to cheat would - this workspace's own attack list from 12 TRU... |
| `means-ends-swap` | Links plan steps by the nouns they share, then swaps means and ends to list steps that serve nothing downstream, steps nothing motivates, and what the final... |
| `opponent-lawyer` | Finds exploitable ambiguity in a rule or contract text - may versus shall, any versus all, an inclusive or, undefined reasonable-type terms, missing time bou... |
| `riffle-order` | Card-magic test hygiene - shuffle a test suite's order k times (seeded), run every test alone as the reference, and classify each test STABLE, VICTIM (fails... |
| `steelman` | Extracts the claims of an opposing text, scores each for strength (number, mechanism, source, specificity), strips strawman markers and overreach and rebuild... |
| `token-bucket` | Rate-limit calls with a token bucket (steady rate + burst capacity) or an exact sliding-window log, per endpoint or API key, with try_acquire(n), an exact wa... |
| `view-from-the-end` | Start from a plan's goal step and back-chain the preconditions each earlier step must deliver, listing unmet preconditions and steps the goal never reaches. |
| `zealot-eye` | Rewrites each claim into its absolutist form (some to all, often to always, may to must) and reports where the amplified claim breaks against counter-evidenc... |
| `rules-binding-audit` | Audit the rule files themselves (DESIGN_HINTS, CLAUDE.md, THE_INVARIANTS, RULES_CARD, shared_claude) rule by rule - who it binds (Claude, the user or the cod... |
| `gradable-acceptance` | Lint a plan's per-item cards so every acceptance line is something a script can decide - each assertion is OK (it carries a hook - inline code, a comparison,... |
| `noise-pick-force` | Test whether a selection procedure (pick the best lookback, parameter, model, universe or screen) is a magician's force - run it on many seeded pure-noise da... |
| `epigenetic-switch` | Change behavior without changing the underlying code/config - keep a frozen base ('genome') and a separate overlay of environment-set marks that switch featu... |
| `max-inbox` | Harvest every item waiting on the user - NEEDS_MAX / "needs the user" / "the user's call" / "OPEN until the user" lines in session ledgers, plans, DECISIONS_... |
| `negative-space` | Diffs a text against a domain checklist for trading claims, plans or code changes and lists the checklist items it never mentions. |
| `restriction-matrix` | The interpretation lock. |
| `rule-conflict` | Read a SET of standing rules (a DECISIONS or DESIGN_HINTS markdown table, list rows with ids like D71, or a folder of rule files) and report where they colli... |
| `forgery-plan` | Take the faker's side of a claimed result - from a few fields (kind backtest / forward record / test pass / model metric / data finding, variants tried, data... |
| `lane-resurrection` | Ask which DEAD trading-lane verdicts have gone STALE - read every lane whose standing verdict is DEAD (through dead-lane-check's lane_verdict reader, source... |
| `outsider-council` | Scores a subject against the concern lexicons of a chef, pilot, nurse, judge and farmer, giving each outsider's coverage, the concern it finds missing and th... |
| `beginners-eye` | Grade each sentence's reading level and list the jargon, acronyms and domain terms a newcomer would need defined, in order of first use. |
| `birds-eye` | Draw the dependency map of a plan or a Python file from above - the roots (nothing above), the sinks (nothing below), the hub with most links, every cycle in... |
| `skill-sync-audit` | Compare the skill libraries (user ~/.claude/skills, <workspace>\.claude\skills, any repo copy) by name and content hash - list skills missing from a root, co... |
| `speed-proof` | How to make code faster WITHOUT changing a single answer, with proof - declare the benchmark before the candidate exists (CPU seconds, min of N), find where... |
| `view-from-zero` | List everything a plan or text presupposes already exists (definite first mentions, re-verbs, possessives, named tools, implied accounts) as if starting from... |
| `cross-cutting-check` | Apply the geologist's law of cross-cutting relationships to an ordered record (DECISIONS.md, errata, numbered plans) - a row may only cite ids defined above... |
| `erase-the-center` | Finds the most central keyword of a text or plan - the one with the widest sentence span (in the most sentences), ties broken by co-occurrence degree (most d... |
| `remove-the-hero` | Extracts the cause and effect sides of the causal statements in a text, deletes the most-cited cause and tests whether any remaining statement still explains... |
| `adversary-eye` | List per plan step what an adversary controls and could tamper with, the check that would catch it, and the first unverified input. |
| `chimera` | Deliberately fuse three or more parents and find where the combination BREAKS - report clashing invariants (one part wants paper-mode, another live-mode) and... |
| `concept-card` | Lint typed concept cards (definition, formal object, theory with a status, assumptions A1..An tagged HOLDS / FAILS / UNKNOWN each with the test that decides... |
| `cross-breed` | Breed two (or more) things - skills, plans, prompts, words, numbers, signals, datasets, anything - into a useful offspring by choosing the REPRODUCTION OPERA... |
| `decorative-check` | Make a forecasting or analytics module prove it beats a flat do-nothing baseline (the expanding mean, or zero) on planted worlds where there IS structure to... |
| `demand-scan` | Route every REAL the user prompt from the transcripts through skill-finder and count, per skill, how many actual asks it would have served (demand), which sk... |
| `depth-in-the-nooks` | Check that every enumerated item of a plan section has its depth line - for each "Depth in the nooks of §X" block find section X, list its numbered items and... |
| `funhouse-mirror` | Scales each weight of an item-scoring rule by ten and by a tenth and lists which conclusions (the leader, the top half, the last place) survive each distortion. |
| `guard-respect` | Find the honest, allowed equivalent when tv-guard (the PreToolUse hook) or the Claude Code auto-mode classifier blocks a command or write - never a disguised... |
| `hl9-rules` | Lint a report to the user or a plan item against the fifteen mechanical rules of HL9 (R1-R15) and print all fifteen rows, so no rule is skipped silently - th... |
| `incubation-card` | Parks a problem as a dated deferred card with a content hash and a fresh-eyes question set built from its own open questions, conditions, numbers and unlinke... |
| `lot-acceptance` | Acceptance sampling for long lists of claims, borrowed from factory quality control - with exact hypergeometric arithmetic say how many of N claims, rows, re... |
| `magicians-force` | Card-magic audit of "random" selections - call a seeded selection function (a subsample, a shuffle null, a bootstrap replicate, a random universe) under many... |
| `oscillatory-stack` | Run and audit the user's Oscillatory Fire stack (Controlled Fire + Fascination Drive + Oscillatory Fire with its 19 hardenings) - keep a JSONL log per cycle... |
| `plan-closure` | Prove a plan file is self-contained - every section pointer has a heading, every item id has a card, every code is in the glossary, and every backticked path... |
| `plant-the-bug` | Prove a new test (or a guard, cache check or shortcut) can actually fail by planting bugs in the code one at a time and watching the tests go red, then rule... |
| `reading-dial` | Let the user choose how literally each prompt is read - four modes from most literal to most interpretive (#code, "#spec" default, "#brief", "#human", or "#d... |
| `reproductive-strategy` | Decide how to generate candidates for a task - clone the best (asexual), cross two parents (sexual, paying the two-fold cost), broadcast many cheap careless... |
| `schema-contract` | Declare a data contract for a feed or table (CSV rows, list of dicts, JSON lines) and enforce it - per-column type (int/float/str/bool/date/ISO datetime), re... |
| `self-attacking-referee` | Make any judge - a significance test, a metric threshold, a "did it beat the baseline" check, a detector, a gate - measure its OWN false-alarm rate and power... |
| `word-sex` | Breed two words into offspring words - the 1-to-1 reproduction operator applied to language. |
| `brittle-test-audit` | Find over-specified tests by making changes that should NOT matter - reorder top-level function definitions, rename locals, reverse dict/set literal order, a... |
| `council-of-views` | Runs N sibling view lenses on one subject and tallies, for each subject keyword or item, how many lenses named it, splitting the subject into agreed, contest... |
| `map-vs-territory` | Compares numbers that docstrings and comments claim (lines, functions, checks, arguments, defaults) with what the code measures by ast, listing drifted claim... |
| `peacock-tail` | Honest-advertising audit of the skill library - for each tool-backed skill, extract what its SKILL.md claims (functions named in code spans and from-imports,... |
| `literal-execution` | Take the user literally - "do this literally, do not talk about it, just do it" - read his prompt as a contract before acting - do the exact verb on the exac... |

## Needs a neighbour

Most skills here run on their own, and seven of them import a sibling that is also in this pack (`pov-core`, `cross-breed`, `literal-execution` and the like), so installing the whole pack covers them. Four scripts import a skill that is **not** in this pack; their SKILL.md still reads fine, but the script stops with `ModuleNotFoundError` until the neighbour sits beside it in `~/.claude/skills/`:

| script | needs | where to get it |
|---|---|---|
| `demand-scan/demand_scan.py` | `skill-finder`, `prompt-genealogy` | `skill-finder` ships in the [skill-maestro](https://github.com/max0wellseltzer-wow/skill-maestro) plugin; `prompt-genealogy` is in the author's library, not yet published |
| `exaptation-finder/exaptation.py`, `peacock-tail/peacock.py`, `rule-conflict/rule_conflict.py` | `skill-finder` | the skill-maestro plugin |
| `lane-resurrection/resurrect.py` | `dead-lane-check` | the author's library, not yet published |
| `pov-core/ratify.py` | `skill-health` | the skill-maestro plugin |

Install skill-maestro first and three of the four work; open an issue if you want `prompt-genealogy` or `dead-lane-check` published too.

## License

MIT; see `LICENSE`. 2026 max0wellseltzer-wow

Built by `pack_build.py` from the maintainer's library; every text file was scrubbed of the maintainer's machine and checked before it was written.
