---
name: cross-breed
description: Breed two (or more) things - skills, plans, prompts, words, numbers, signals, datasets, anything - into a useful offspring by choosing the REPRODUCTION OPERATOR that fits, then keeping the child only if it shows hybrid vigor. Use this whenever the user wants to combine, merge, hybridize, cross-pollinate, fuse, or "have X and Y reproduce", asks for the offspring of two ideas/tools/artifacts, wants new skills bred from existing ones, or says cross-breed / cross-pollinate / sex / reproduce / mate / hybrid - and to breed a whole POPULATION of candidate skills at once ("fill the soup", "breed more skills", "generate candidates toward the 500"). The broad parent skill of word-sex, word-sex, word-sex, and signal-fusion.
---

# cross-breed

"Combine two things" is not one move. In nature a thing's offspring depends entirely on HOW it reproduces, and that is the design method here: pick the reproduction operator that fits the two parents and the coverage you want, produce the child, then prove it earns its place. This is the broad "pollination" skill - wide coverage - that the specific "sex" skills (word-sex, word-sex, word-sex, signal-fusion) are instances of.

## Step 1 - pick the mode

- **BROAD (pollination)** when you want one parent's discipline spread across many targets (wide coverage, thinner than either parent).
- **1-TO-1 (sex)** when you want ONE specific new thing from a particular crossing of two parents.

## Step 2 - pick the reproduction OPERATOR (it dictates how the parents combine)

| Operator (from) | Combines two parents by... | Good when |
|---|---|---|
| **sexual crossover** (fauna) | splicing head of one + tail of the other at a seam | words, phrases, names, sequences |
| **mediant / means** (number) | the value that sits between, or blends magnitude/rate | numbers, ratios, rates |
| **heterosis / fusion** (hybrid vigor) | averaging two independent streams; keep only if the child beats both | signals, estimators, votes |
| **pollination** (flora, broadcast) | carrying one parent's trait onto many targets | spread a practice across lanes |
| **grafting** (horticulture) | a new scion on a proven rootstock | a new idea on mature infra |
| **conjugation** (bacteria) | passing ONE portable capability (a "plasmid") laterally | reuse a single guard/util |
| **reassortment** (virus) | swapping whole modules between two pipelines | compare interchangeable parts |
| **symbiogenesis** (cell) | one parent permanently absorbs the other as an organelle | merge a helper into a host |
| **meiosis** (reduce+recombine) | halve each to essentials, recombine the cores | breed two bloated things into one lean one |

(The fuller operator library and a graded candidate catalog live in `CROSS_POLLINATION_SKILLS_2026-10-13.md` in the Autotrade repo - the build queue for new bred skills.)

## Step 3 - prove the child earns its place (hybrid vigor, or cull)

A cross is only worth keeping if the offspring beats BOTH parents on the metric you care about - that is heterosis. A child thinner than either parent is **outbreeding depression**: drop it. A child that merely looks like a trusted parent to borrow its authority is **mimicry**: distrust it. And a "child" that is really one parent lightly edited is **sterile**: it did not reproduce, it copied. Keep only genuine, vigorous offspring; record the culls (they are findings, not waste).

## Worked offspring (already built)

`word-sex` (word x word), `word-sex` (phrase x phrase), `word-sex` (number x number via mediant/means), `signal-fusion` (signal x signal with a vigor gate). Each is this method with one operator fixed. To breed a NEW skill, name the two parents, pick the operator, build the smallest offspring that beats both, and give it its own failing-capable selftest before you believe it.

## The tool (ships with this skill)

```
from breed_plan import choose_operator, vigor
choose_operator("signals", "1:1")   # operators that fit, with the sibling tool for each
vigor(parent_a, parent_b, child)    # KEEP / STERILE / DEPRESSION
python breed_plan.py --selftest     # 7/7
```
`breed_plan.py` maps what the parents are (words, numbers, signals, modules, skills...) and the mode to the fitting operators and their implementing skills, then judges the offspring: keep it only on hybrid vigor.

## Population breeding (merged from skill-soup)

One cross gives one child; a soup gives a population. `skill_soup.py` crosses every unordered distinct pair of parent skills (culling self-pairs and duplicates), rotates through the operator table so the population is varied, and names each child via **word-sex** (fallback: a splice). Pure stdlib, deterministic, selftest 6/6.

```
python skill_soup.py forward calibration harvest signal memory   # breed all pairs -> named candidates
from skill_soup import soup
pop = soup(parent_skill_names)     # [{name, parents, operator, blurb}, ...]
```

Output is CANDIDATES, not built skills: a soup is selection, not result. Most should be culled; for each worth pursuing apply Step 3 (vigor or cull) and give it a failing-capable selftest before it becomes a skill. Survivors queue in `CROSS_POLLINATION_SKILLS_2026-10-13.md`; `broadcast-spawn` is the gate that culls a soup down.
