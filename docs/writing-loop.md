# Iterative writing convergence

Pi's internal implementation is not public. The observable behaviour is a
generate → critique → revise loop with a stopping rule. It can be reproduced
without treating self-review as truth.

## State

```text
DraftState
  version
  text
  claims[]
  citations[]
  issues[]
  scores{}
  best
```

Hard gates:

```text
every claim traceable
no generated citation
no unsupported number
```

A candidate that fails a hard gate is never selected, even if it reads better.

## Loop

```text
draft
→ independent critic
→ issue list
→ targeted rewrite
→ deterministic checks
→ rubric score
→ compare with best
→ stop or repeat
```

Rules:

- keep the best draft, not the latest draft
- accept only if score improves and hard gates still pass
- no fact or citation may be introduced by the writer
- maximum 3 rounds
- stop when score is stable, threshold reached, or budget exhausted
- if a round fails, revert to best

## Rubric

```text
Thesis and argument        20
Structure and transitions  20
Evidence traceability      25 (hard gate)
Readability                15
Citation selectivity       10
Figures and tables         10
```

Penalties:

```text
paper-by-paper list
citation carpet
unexplained jargon
abstract that repeats the body
figure caption without takeaway
```

## Critics

Use separate passes:

```text
Fact critic       only checks claims/citations
Structure critic  only checks argument and section flow
Reader critic     asks whether a non-specialist can follow the first two pages
Style critic      checks Perspective anti-patterns
```

Do not ask one pass to do everything. Separate critics produce more actionable
issues.

## Why it converges

It does not converge because the model "thinks harder". It converges because:

1. the objective is explicit
2. evidence is fixed before writing
3. bad candidates are rejected
4. the best draft is retained
5. the loop has a hard cap

Without these, self-iteration becomes cosmetic rewriting or citation drift.

## Report integration

```text
L1/L2/L3 evidence
→ thematic clusters
→ thesis
→ outline
→ section drafts in parallel
→ merge
→ fact critic
→ structure critic
→ reader critic
→ style critic
→ targeted rewrite
→ rerun deterministic checks
→ best draft
→ render
```
