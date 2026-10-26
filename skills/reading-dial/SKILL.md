---
name: reading-dial
description: Let the user choose how literally each prompt is read - four modes from most literal to most interpretive (#code, "#spec" default, "#brief", "#human", or "#dial 1-4", or "read as code/human") - per prompt, sticky for the rest of the conversation ("#code on", "from now on read as human"), cleared with "#off", or saved as a default across sessions. Detects the marker, strips it, dispatches to the right reader, and shows what that reading binds; ambiguity() scores 0-1 how differently the four modes bind a prompt and names the marker that resolves it. Use this at the start of every the user prompt to check for a reading marker, whenever he says I'm being too literal / not literal enough / you took that wrong / read it like code / read it like a person / switch modes, and when deciding how much to infer from a prompt. Pairs with read-as-code, read-as-spec, read-as-brief, read-as-human and literal-execution.
---

# reading-dial

the user, 10-16: *"usually I actually do know when I have to worry about you taking me too literally and when I have to worry about you not taking me literally enough."* So he chooses, and the dial makes the choice cheap: one marker.

| Marker | Mode | Reads | When to reach for it |
|---|---|---|---|
| `#code`, `#dial 1`, "read as code" | read-as-code | every word is binding; gaps are errors, so ask | precise operations: files, rows, git, commands |
| `#spec`, `#dial 2` (**default**) | read-as-spec | explicit words binding; gaps filled and **stated** | most work prompts |
| `#brief`, `#dial 3` | read-as-brief | purpose first; hard limits binding; method free | creative tasks with a few firm limits |
| `#human`, `#dial 4`, "read as human" | read-as-human | spirit, emotion and hyperbole as signal | visions, brainstorms, venting |

- **Per prompt:** a marker anywhere in the prompt applies to that prompt only.
- **Sticky:** `#code on` or "from now on read as human" holds until `#off`. A per-prompt marker still overrides a sticky mode for one prompt, without clearing it.
- **Default across sessions:** `set_default("brief")` writes `~/.claude/reading-mode.json`.
- **Always code-level, whatever the mode:** the exact target of anything destructive or outward-facing (delete, push, post, the pen), plus the user's standing rules (paper only, keys, the pen).

When a reading goes wrong, say which mode was used. If the same kind of prompt keeps going wrong, suggest the marker that would have fixed it.

## The tool (ships with this skill)

`dial.py` - pure stdlib, imports the four readers, selftest 8/8:

```
from dial import dispatch, set_default, get_default
out = dispatch(prompt, state)      # mode, reading, state (carry it to the next prompt), marker, cleaned_prompt
python dial.py "#code delete row D70 from DECISIONS.md"
```

## Ambiguity meter (merged from ambiguity-meter)

Seed: the user's metaphorical questions crossed with "prompts having sex" and the dial itself. `ambiguity(prompt)` reads a prompt in all four modes and measures how differently they bind it. It flags unresolved references and undefined quantities (code errors), hyperbole and soft asks (human signals), a vision with no concrete command, and a brief purpose that differs from the first command. The score is 1 - prod(1 - weight) over the flagged phrases, from 0 to 1. It returns the phrases and the marker that would resolve them: "this needs #code" (name the referent, or ask) when code errors dominate, and "this needs #human" when human signals dominate.

```
python dial.py --ambiguity "fix that and add some tests"      # 0.58, needs #code
```

On 2026-10-15, three real the user prompts scored as follows. "Delete the D70 row from DECISIONS.md" scored 0.00. "no keep working on them and build the ones that are obviously ready" scored 0.35 (#code, 'them'). "you are giving me literally hundreds more skills, keep going" scored 0.51 (#human, 'literally hundreds'). The meter is cue-based like the readers, so treat it as a prompt to state the reading, not as a verdict.

## Uses and limits

In a conversation, the sticky state lives in what I remember from earlier turns. The tool's `state` dict is for scripted runs. The readers are cue-based helpers: the mode sets my *stance*, and the tools surface what that stance binds.
