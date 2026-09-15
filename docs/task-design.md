# Designing tasks that teach useful presentation skills

REFRACT automates compilation and checking. Selecting good scoring points remains an agent
decision grounded in each presentation. A large task count alone is not evidence of quality.

## What to borrow from production experience

- Start with a specific relationship: a chart's categories and values, a table's row meaning,
  an arrow's attached target, or an object's alignment. Make the corruption visible enough
  that someone comparing the init and reference can identify the repair.
- Spread credit across distinct skills. Treat a single operation consuming most of the reward
  as a design warning. Aim for no more than 20% per narrow skill in a large mixed task, but do
  not invent filler to meet a fixed family count. This is review guidance, not a compiler gate.
- Reconstruct editable objects. Picture replacement, table content, native chart data and
  connection semantics should not collapse into “paste a screenshot of the answer.”
- Only score facts recoverable from supplied evidence. Do not introduce hidden exact font names,
  native style IDs, or an editor's serialization choices as reconstruction requirements.
- Permit equivalent rebuilt objects. Runtime assignment is semantic and one-to-one; original
  IDs select mutations during generation, not the only valid objects in a solution.
- Keep instructions short but explicit about input locations, final filename, editability and
  preservation. The desktop adapter appends concrete deployment paths.
- Code-enabled solving is supported. Evaluate the final artifact; do not label legitimate code
  editing as a hack. Test simple scripted strategies when calibrating difficulty.

## Before accepting a scoring point

Test real candidate files, not composite screenshots with a score label. Include:

1. Untouched init and complete oracle.
2. One honest repair with other mutations still present.
3. Wrong content in the right place; right content in the wrong place.
4. Equivalent replacement with new IDs, and target-editor save/reopen.
5. Relevant attacks: duplicate objects, wrong asset, extra chart series, altered numeric
   formatting, deleted protected content, and screenshot substitution.

The built-in red-team covers only a subset: object-ownership coverage, isolated repairs,
slide reordering, and protected-object movement. Extend it for each new capability. Neither
`Init=0 / Oracle=1` nor a synthetic smoke test proves all equivalent solutions score fairly,
that a task is hack-proof, or that it reaches a particular rollout length/score.

## Available operation parameters

Indices are zero-based; slide numbers are one-based. Dimensions and offsets are in points.
Use inventory selectors, and consult the generated prompt for allowed family/component pairs.

| Operation | Parameters beyond `type` |
|---|---|
| `move_shape` | `dx_points`, `dy_points` |
| `resize_shape` | `scale_x`, `scale_y` (each between 0.05 and 20) |
| `swap_geometry` | `other_shape_id` on the same slide |
| `change_z_order` | absolute `index` or relative `delta` |
| `remove_shape` | none |
| `set_text` | `text` |
| `set_fill` | `rgb`, six hexadecimal digits |
| `set_chart_value` | `series_index`, `point_index`, `value` |
| `set_series_color` | `series_index`, `rgb` |
| `remove_chart_title`, `remove_chart_legend` | none |
| `set_table_cell_text` | `row`, `column`, `text` |
| `set_table_cell_fill` | `row`, `column`, `rgb` |
| `set_table_column_width` | `column`, `width_points` |
| `set_table_row_height` | `row`, `height_points` |
| `reverse_connector` | none; swaps attachments and arrowheads |
| `detach_connector_endpoint` | `endpoint`: `start` or `end` |
| `set_connector_arrowhead` | `endpoint`: `start` or `end`; `arrow_type` |

New capabilities need inventory evidence, proposal validation, mutation, scoring, positive
equivalence tests and adversarial tests. Register them centrally. Do not add one-off hidden
evaluators for individual source decks.

## What this release does not yet establish

Recursive group topology, SmartArt, equations, animation timing and Morph do not have complete
scoring contracts here. Explicit run/paragraph styles and simple embedded chart workbook ranges
are supported; inherited/theme typography and formula-backed workbook calculations are not.
Image identity still uses a coarse signature fallback; it does not prove asset provenance or
defeat all PDF-crop attacks. Theme colors and all editor-specific visual equivalents are not
fully normalized. Z-order scoring is not a complete rendered occlusion check.

Do not advertise those capabilities as covered just because a deck contains them. The inventory
coverage invariant covers inventoried top-level objects, not every child or non-shape part.
Choose supported tasks for initial deployment and retain review plus real-editor canaries.
See [the capability matrix and additional operations](capabilities.md). The authoring prompt
includes the full argument catalog; use `refract capabilities` to inspect it independently.

## Trainable progress and operational failures

Grade repaired content relative to its damaged baseline. A small unrelated edit should reduce
credit gradually, not erase the whole task. Hard gates are reserved for the implemented
catastrophic cases; inspect the detailed score output when tuning preservation penalties.

An infrastructure failure is not evidence that an agent answered incorrectly. The adapter
raises collection/setup/runtime failures for the host to retry; configure your host accordingly.
An invalid submitted PPTX can be reported as an agent-output failure. Always verify the saved
file on disk after closing the editor, not only the currently visible WPS session.
