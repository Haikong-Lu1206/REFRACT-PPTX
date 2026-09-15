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
- `table_structure`, `table_content`, `table_style`, `table_proportions`: row/column and merge
  structure, cell text, cell fill/borders, and normalized row/column dimensions.
- `connector_targets`, `connector_style`: semantic endpoint objects and connection sites plus
  arrowheads, line preset, width, and color. Endpoint identity is resolved through the attached
  objects' semantic keys rather than fixed shape IDs.

## Additional visible contracts (plan 1.1)

- `rotation`: shortest circular angle difference; full credit within 1 degree, zero at 20 degrees.
- `flip`: horizontal and vertical states must both match.
- `picture_crop`: maximum crop-edge error; full within 0.5 percentage points, zero at 15 points.
  Picture transform scores are multiplied by media identity similarity.
- `shape_preset`: native preset equality. `line_style`: mean of visible state, dash, RGB and
  width similarities; width is full within 0.25pt and zero at 3pt error. RGB uses maximum-channel
  error, full within 8 and zero at 64; this is not a perceptual color metric.
- `font_size`: character-weighted similarity, full within max(0.75pt, 3%), zero at max(4pt, 30%).
  `text_color` uses the RGB tolerance above; `text_emphasis` checks known bold/italic/underline.
  Text must remain identical for these formatting components; run segmentation may change.
- `paragraph_alignment`, `paragraph_bullet`: equality of known explicit paragraph properties.
  Bullet font is omitted. `paragraph_indent`: margin/indent full within 1.5pt, zero at 18pt.
- `chart_direction`, `chart_grouping`, `chart_legend_position`, `chart_markers`: native display
  properties conditioned on chart-data similarity. Verified embedded workbook/cache consistency
  is an episode-local requirement; cache-only repairs cannot receive chart credit.

These are component similarities **before Init normalization**. A smaller residual error only
receives partial progress when it improves on the actual initial state. The thresholds are
documented implementation choices, not measured GUI accuracy guarantees.

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
