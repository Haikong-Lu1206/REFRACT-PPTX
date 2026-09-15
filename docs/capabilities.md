# Capability matrix and migration scope

REFRACT 0.7 brings static reconstruction, spatial repair and native-chart techniques into one
neutral factory. It has 33 registered operations. Each new operation has inventory evidence,
proposal validation, a deterministic mutator, a scoring component and synthetic regression cases.
Run `refract capabilities --output capabilities.json` for the current argument catalog.

## Added in 0.7

| Area | Operations | Scoring and supported evidence |
|---|---|---|
| Picture transforms | `set_rotation`, `set_flip`, `set_picture_crop` | Identity-conditioned rotation, flip state and per-edge crop; does not require the original shape ID |
| Shape/line appearance | `set_shape_preset`, `set_line_style` | Preset shape, line width, explicit RGB and dash; no arbitrary custom geometry conversion |
| Text appearance | `set_font_size`, `set_text_color`, `set_text_emphasis` | Character-aligned styles; splitting an equivalent run is accepted; source attributes must be explicit |
| Paragraph structure | `set_paragraph_alignment`, `set_paragraph_bullet`, `set_paragraph_indent` | Explicit paragraph alignment, bullet character/type and margins; bullet font family is not compared |
| Chart presentation | `set_chart_direction`, `set_chart_grouping`, `set_chart_legend_position`, `set_chart_marker` | Native plot group and data must remain valid; bounded single-plot variants |
| Chart data consistency | Extended `set_chart_value` | Update cache and embedded workbook cell together; verified source workbooks require consistent candidate data |

All operations also use normal task compilation, Init/Oracle checks, isolated-repair red-team,
resumable builds and the packaged desktop evaluator. Mutation design remains an agent decision.
Mix changes that matter to the deck; do not repeat the same conspicuous color or geometry error
just because it is easy to generate. The parameter catalog is included in the design prompt.

## Limits enforced before generation

- Visual mutations currently target top-level native shapes, pictures and connectors, not group children.
- Preset changes use a bounded shape list. Custom geometry needs its own contract.
- Line mutations require an explicit RGB source line; unresolved theme inheritance is rejected.
- Text format mutations require explicit source run or paragraph-default attributes. Paragraph
  alignment, bullet and indent mutations likewise require explicit source evidence. No exact
  font-family requirement is inferred from a PDF. Reference inspection remains part of blind review.
- Chart display mutations require one plot group. Marker changes target line/scatter series.
- Chart data edits support literal values or readable embedded XLSX single-column ranges.
  External, unsupported or inconsistent sources are rejected. Formula-backed cells require an
  editor/calculation engine and are outside this implementation.

## Version and behavior changes

New plans use `plan_version: 1.1`; proposal syntax remains `1.0`. New snapshots contain visual,
typography and chart-display/workbook evidence. Readers tolerate older snapshots with absent
fields, but the new compiler always produces the richer inventory.

Protected-object checks now include recorded rotation/flip/crop/preset/line and explicit run
formatting. Target and protected objects share one assignment, so one candidate cannot satisfy
both roles. These changes can reduce scores for collateral damage previously unmeasured.
Rebuild and revalidate task bundles to adopt them; do not replace hidden runtimes in existing
experiments without recording the version change. Earlier deployments keep their packaged runtime.

For a chart whose source workbook was verified consistent, a mismatched, missing or unreadable
candidate workbook gives that chart episode zero. This is not a deck-wide hard gate. Native
chart display credit is also conditioned on retained chart data. Styles cannot compensate for
replacing the actual values.

## Still outside the supported contracts

| Capability | Why it is not advertised as complete |
|---|---|
| SmartArt semantic/topology reconstruction | Needs graph matching and consistency with editor-generated drawing caches |
| Nested groups and rendered occlusion | Needs recursive coordinate transforms and a rendering-based visibility check |
| Equations | Needs native math equivalence and editor rendering verification |
| Animation, click groups, motion paths, transitions and Morph | Needs target/order/timing contracts and real playback acceptance |
| Theme/inherited fonts and full visual styling | Needs layout/master/theme resolution and target-font rendering evidence |
| Arbitrary chart structural rewriting | Needs multi-plot/axis/series relationships and workbook synchronization beyond simple ranges |

These are remaining implementation areas, not supported names in a catalog. The production
methodology is broader than the current open-source contracts. See [compatibility](compatibility.md)
for target-editor acceptance; synthetic tests alone do not establish real WPS behavior.
