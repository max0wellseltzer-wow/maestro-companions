---
name: council-of-views
description: Runs N sibling view lenses on one subject and tallies, for each subject keyword or item, how many lenses named it, splitting the subject into agreed, contested and ignored elements. Use this whenever the user wants a vote of several points of view on what in a note or ranking matters. Pairs with lens-carousel, random-lens, vantage-rotation and pov-core.
---

# council-of-views

A PLURAL lens of the point-of-view family (engine: pov-core). It seats N sibling lenses around one subject and counts votes element by element. The elements are the subject's top keywords, or its item labels. Each element lands in one of four bins: agreed (named by at least half the council), contested (2 or more lenses but under half), lone (exactly one lens, the dissent, with the dissenter named) or ignored (no lens named it, the council's shared blind spot). lens-carousel compares lenses with each other. This lens compares what they say about the subject's parts.

## The tool (ships with this skill)

```
python council_of_views.py --selftest
python council_of_views.py <subject> [--opt n=7 | --opt lenses=spotlight,squint,skeptic-eye] [--json]
```
```python
from council_of_views import apply
v = apply(text, n=7); v["stats"]["bins"], v["stats"]["tally"], v["stats"]["council"]
```
The council is fixed. N seats are spread evenly over the sorted family, and each seat takes the next lens that can read the kind. Meta lenses (lens-carousel, random-lens, this one) never sit.

Example: `[council-of-views] (code) council of 7 on 13 elements: 3 agreed, 4 contested, 3 lone dissent, 3 ignored`

## Uses and limits

- A vote means the lens mentioned the word (whole-word match), not that it judged it important or good.
- Reads text, plans, code and items. A series has no named elements, so it is refused.
- It costs N sibling runs. The seats change as the family grows, so pass `lenses=` to repeat a comparison.
- The minority-report idea (keep only lone dissent) is folded in here as the `lone` bin.
