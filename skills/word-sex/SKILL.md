---
name: word-sex
description: Breed two words into offspring words - the 1-to-1 reproduction operator applied to language. Two parents cross over at vowel-group seams (smoke x fog -> smog, breakfast x lunch -> a brunch-like child) and only pronounceable, novel offspring survive. Use when the user wants a name, a portmanteau, a coinage, a product/skill/project name, a blend of two terms, or to demonstrate that "anything can reproduce"; and as the worked 1-to-1 example of the cross-pollination method (CROSS_POLLINATION_SKILLS). Also (formerly phrase-sex) - "Breed two phrases or sentences into offspring phrases". Also (formerly number-sex) - "between"; "Breed two numbers into offspring numbers". Pairs with fascination-forge.
---

# word-sex

The purest proof that reproduction is a general design operator, not a biology fact: the parents are *words*. Two words cross over at their vowel seams and bear a child that is neither - a 1-to-1 "sex" offspring (one specific new thing), not broad coverage.

## The tool (ships with this skill)

`word_sex.py` is the implementation - pure stdlib, deterministic, with a selftest that reaches a real portmanteau and proves the pronounceability gate can fail:

```
python word_sex.py skill sex            # ranked offspring (word <tab> score)
python word_sex.py breakfast lunch 5    # top 5
python word_sex.py --selftest           # 6/6 (incl. smoke x fog -> smog; gate rejects a consonant pile-up)
from word_sex import breed, is_pronounceable
```

`breed(a, b, n)` crosses the parents at vowel-group boundaries in both directions, filters to pronounceable + novel children, and ranks by a seam-pivot bonus, length naturalness, and whether the child carries a chunk of each parent.

## The method behind it (reproduction as a combination operator)

This is one entry in a larger idea: how a thing REPRODUCES dictates how two parents combine. Sexual recombination = crossover → one novel offspring (`word-sex`). Pollination = broadcast one trait across many (broad-coverage skills). Grafting = scion on rootstock. Conjugation = a portable "plasmid" capability passed laterally. Reassortment = swap whole modules. See `CROSS_POLLINATION_SKILLS_2026-10-13.md` for the full operator library and the graded candidate catalog.

## Honest limits

It is a creativity generator, not a lexicon: offspring are candidates to pick from, not guaranteed real words, and the vowel-seam rule reaches many but not all classic portmanteaus (it cuts after vowel groups, so pre-vowel cuts like "br" + "unch" are out of reach). Pick the child you like; it does not grade meaning.

## phrase-level crossover of two texts (merged from phrase-sex)

Phrases reproduce the way words do, one level up: cross two parents at their word seams and a child carries a head clause from one and a tail clause from the other. Many children are awkward; a few are the hybrid you wanted. It is a candidate generator for taglines, titles, and mottos - you pick the keeper.

### The tool (ships with this skill)

`phrase_sex.py` - pure stdlib, deterministic, selftest 5/5:

```
python phrase_sex.py "the quick brown fox" "jumps over the lazy dog"
from phrase_sex import breed
```

`breed(a, b, n)` crosses the two phrases at word boundaries in both directions and keeps novel children that **blend** - each must carry at least one word from EACH parent, so a child is never just one parent lightly edited. It ranks by length naturalness and a seam-pivot bonus (the two clauses meeting on a shared word, like a creole's pivot term).

### Honest limits

A creativity generator, not an editor: offspring are raw candidates, some ungrammatical - skim and pick. It crosses at word boundaries only (it will not reorder within a clause or inflect words to agree). For blending single words, use **word-sex**; for a broader method of breeding any two artifacts, see **cross-breed**.

## number crossover by mediant and digit splicing (merged from number-sex)

Two numbers can bear a child, and WHICH child depends on how you let them reproduce. A mediant sits between them the way a Farey fraction does; a geometric mean blends their magnitude; digit crossover splices their base-10 genome. The point is that "combine two numbers" is not one operation - it is a family of offspring, and you pick the one whose property you want.

### The tool (ships with this skill)

`number_sex.py` is the implementation - pure stdlib, deterministic, selftest 6/6:

```
python number_sex.py 1/2 1/3     # mediant 2/5, means, digit crossover (accepts ints, decimals, fractions)
python number_sex.py 2 8
from number_sex import mediant, children, digit_crossover
```

- **mediant(a, b)** = (num_a+num_b)/(den_a+den_b) - the child that lies strictly between the parents; this is how the Stern-Brocot / Farey tree reproduces and how you find the simplest fraction in an interval.
- **means** - arithmetic (the midpoint), geometric (blends magnitude; the right "average" for ratios/growth), harmonic (the right "average" for rates).
- **digit_crossover(a, b)** - interleaves the parents' digits, a genetic crossover on the number's base-10 genome.

### When to reach for which child

Pick the offspring by the property you need: a value *between* two fractions in lowest terms → mediant; an average of rates/speeds → harmonic; an average of growth factors or a blend of magnitudes → geometric; a plain midpoint → arithmetic. That is the whole skill: the parents fix the material, the reproduction mode fixes the child.
