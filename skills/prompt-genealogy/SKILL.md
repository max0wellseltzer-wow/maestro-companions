---
name: prompt-genealogy
description: Trace a theme through the user's own prompts - give keywords or a regex and get a dated timeline (earliest first) of every real the user prompt across all session transcripts that mentions it, with redacted quoted excerpts, plus the first appearance of each keyword; memes() traces phrases one speaker coined and the other adopted (the user and Claude's shared vocabulary). Use this whenever the user asks where an idea came from, when he first asked for X, how a theme (sex/mutation/flora, living prompts, evolution...) grew across sessions, or before a skill wave to cite the prompt that caused it. Pairs with transcript-miner, rule-miner, lineage-ledger and collision-registry.
---

# prompt-genealogy

Skills come in waves, and each wave starts with a phrase the user typed. This finds those phrases: it reads every transcript under `~/.claude/projects`, keeps only the user's real typed prompts (not reminders, slash-command bodies, peer-session notes, skill loads, continuation summaries, sidechains or tool results), de-duplicates the copies that resumed sessions make, and prints when each matching prompt was said and in which session.

## The tool (ships with this skill)

`genealogy.py` - pure stdlib + transcript-miner's `redact`, selftest 8/8:

```
python genealogy.py "sex|reproduc|flora|fauna|mutation"             # all transcripts
python genealogy.py "living prompt" some.jsonl folder/ --max 40 --context 100
python genealogy.py "hybrid" --json                                  # machine-readable
from genealogy import iter_prompts, genealogy                        # reuse the the user-prompt reader
```

The keywords for the first-appearance table are the top-level `|` alternatives of the pattern (matching is case-insensitive). Default `--max 60` timeline lines; the cut is reported.

## Memes (merged from meme-tracker)

`memes(paths)` traces the co-evolution of a shared vocabulary. It looks at phrases of 2 to 4 words that never end on a stopword and never start on one except "the". It replays every the user prompt (the reader above) and every main-thread assistant text record in time order. For each phrase, it reports who used it first (the user or Claude), when the other speaker first adopted it, and how many of the adopter's turns used it after that. The candidates are phrases the user used at least once, which keeps memory bounded on huge assistant logs. A shorter phrase with exactly the same history as a longer one that contains it is dropped.

```
python genealogy.py --memes                      # all transcripts, top 50 by adoption count
python genealogy.py --memes some.jsonl --max 20 --json
```

The first real run, on the 95 MB 10-06..10-15 session, put "state packet" first: the user said it at 04:09 on 10-06, Claude adopted it 10 minutes later, and Claude then used it in 45 turns. Generic phrases such as "the file" also rank, so read the list for coined terms. Adoption here means the words were reused, not that the meaning was shared.

## Uses and limits

Use it to cite the prompt behind a skill (lineage-ledger), to see whether a theme is new or a repeat, and as the shared reader for rule-miner. It is a regex search: synonyms you did not list are missed, and a keyword like `sex` also hits "sextant" unless you write `\bsex`. Transcripts cover only what is on this PC; timestamps are UTC minutes. A full scan of ~500 MB takes a minute or two and streams line by line (safe on 3.9 GB RAM).
