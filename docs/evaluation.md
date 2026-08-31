# Evaluation

REFRACT scores repair progress relative to the damaged init, not absolute resemblance alone.
For a component similarity `s`, the normalized progress is:

```text
progress = clamp((s(candidate, oracle) - s(init, oracle))
                 / (1 - s(init, oracle)), 0, 1)
```

This makes the generated init score zero and a valid oracle score one while preserving partial
credit. Components and episodes are weighted averages. Preservation and large-image checks are
applied afterward as multipliers; catastrophic structural gates are applied last.

## Matching

Objects are matched per slide and native kind using a maximum-weight one-to-one assignment.
Text, media, chart data, semantic keys, names, and stable IDs contribute matching evidence.
A stable ID helps locate an object but does not prove that protected visible content is intact.
Geometry swaps include both targets in the same assignment and score both ends.

## Components

- `existence`: whether a uniquely matched target exists.
- `geometry`: center position and width/height. Position is full at 0.5% of the slide diagonal
  and reaches zero at 4%; size is full within 2.5% and reaches zero at 15% relative error.
- `text`: normalized visible text similarity.
- `fill`: exact/theme token equality or continuous RGB distance.
- `media_identity`: exact SHA-256 or a 12x12 RGB visual-signature fallback. Visual similarity
  is full at 0.985 and reaches zero at 0.80.
- `z_order`: graded distance in the slide shape tree.
- `chart_type`, `chart_data`, `chart_elements`, `series_style`: native chart plot type, series
  names and cached values, title/legend presence, and series colors.

## Preservation and gates

Every untargeted top-level visible object becomes a protected contract. Text, fill, geometry,
picture content, and native chart semantics are compared independently of ID continuity. Losses
are graded and capped so small collateral changes do not immediately zero the task.

Unexpected objects receive a progressive penalty. Pictures above 40% slide coverage receive a
continuous penalty, reaching zero at 80%. A picture is exempt only when it strongly matches an
expected picture and its geometry is at least 0.95 similar to the expected box.

Slide count, relationship order, slide size, and unauthorized pictures covering at least 80% of
a slide are catastrophic hard gates. These represent changed task structure or reference-paste
behavior, not ordinary editing imprecision.
