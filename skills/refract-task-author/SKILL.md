---
name: refract-task-author
description: Design and validate editable PPT reconstruction tasks using REFRACT. Use for preparing source decks, creating per-deck mutation proposals, and building task batches; not for solving a benchmark task or making an ordinary presentation.
---

# Author REFRACT tasks

Use the installed `refract` CLI (`python -m refract_pptx` is equivalent). Check `refract --version`
and `refract --help` first. This skill requires REFRACT; it does not include an Office editor,
model credentials or source presentations.

For a new collection, run `refract init-workspace PATH`. For each source, run:

```text
refract prepare-task SOURCE.pptx --reference REFERENCE.pdf --output PATH/designs/NAME --source-uri SOURCE_URI --license LICENSE
```

Omitting `--reference` asks local LibreOffice to export it. Use a PDF from the target editor if
its rendering differs. Source files must be supplied or authorized by the user; do not infer
redistribution permission from their availability online.

Read that design's `HANDOFF.md`, `design-prompt.txt`, and `objects.json`. Inspect the actual
reference pages and source objects. The prompt lists supported capabilities; do not invent
an unsupported evaluator to force a proposal through.

Write `proposal.json` in the design directory. Choose changes that expose meaningful relationships
in this specific deck. Spread credit across distinct skills when the source supports it; avoid
filling a quota with repetitive picture deletion or color changes. Every intended correction
must be inferable from reference, init, instruction, materials or intact repeated patterns.

Keep the instruction at the macro level and preserve editable content. Target IDs identify
objects for mutation, not the only acceptable solution. Do not require hidden font/style IDs
that a solver cannot recover from the reference. Code-based solving is legitimate.

Run `refract workspace-status PATH`. Correct the proposal if it is rejected; do not weaken the
evaluator or edit the source just to make a check pass. Then run `refract build-workspace PATH`.
Inspect per-task errors and the bundle's `validation/build.json` and `validation/redteam.json`.
An untouched init must score zero, the source oracle full credit, and honest isolated repairs
must receive positive credit. These checks do not prove difficulty or universal editor tolerance.

Before a production release, obtain an independent review with only solver-visible files and a
real target-editor save/reopen comparison. Do not claim you watched an animation or opened WPS
unless you did. Use `record-blind-review`, `record-office-roundtrip`, then `release-desktop`.
Do not register synthetic self-comparisons as real Office evidence.

Hand off bundle locations, validation results, remaining limitations and a small diverse canary
set. Publish/deploy externally only within the user's authorization. Keep source decks, plans,
oracle inventories and evaluator runtime out of the solving agent's public materials.
