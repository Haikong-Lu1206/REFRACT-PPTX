# Native SmartArt repair

SmartArt support is available in the current source under `reference_reconstruction`, capability
`smartart_semantic_repair`. Run `refract capabilities` to inspect the operation arguments.
Mutation choice still belongs to the design agent after inspecting the rendered reference.

| Operation | Change |
|---|---|
| `set_smartart_text` | Replace or erase one node's label |
| `swap_smartart_text` | Exchange two different node labels while retaining their visual slots |
| `set_smartart_fill` | Change one node's explicit RGB fill |

`node_index` selects a zero-based preorder node from the SmartArt inventory. Swaps also take
`other_node_index`; replacements take `text`; fill changes take `rgb`. These selectors are used
to generate the mutation, not to demand that a solver retain IDs.

All three operations use `scoring: {"smartart_structure": 1.0}`. The mutator updates both the
semantic model and its cached drawing. Unsupported models are rejected before generation with
an inventory reason, rather than silently downgraded to ordinary text boxes.

## How scoring works

Nodes are aligned by their ordered path from the semantic document root. Parent-child edges,
sibling order and node counts therefore affect correspondence. IDs, XML prefixes and text-run
segmentation are not compared. Whitespace is normalized; Unicode symbols, case and numeric
formats remain significant (`1` differs from `1.0`).

For each matched node:

```
node score = correct semantic AND displayed label
             × normalized node geometry
             × supported visible style
diagram score = mean node score × node-count completeness × outer-frame geometry
```

Missing nodes score zero. Extra nodes reduce node-count completeness. A correct hidden label
with an incorrect display cache receives no content credit. Text-only repairs cannot compensate
for all nodes having the wrong size, position or shape. Flattened drawings/images without the
native diagram model cannot satisfy this contract.

Node positions apply the cache's group transform, then normalize to the outer frame. With no
group transform, frame-local coordinates are used. Full position credit is within 0.5% of the
normalized frame unit, falling to zero at 4%; size error is full within 2.5%, zero at 15%.
Rotation tolerates 1 degree, falling to zero at 20 degrees; flips and shape presets must match.
Explicit RGB fills tolerate maximum channel error 8, falling to zero at 64. These are engineering
tolerances, not claims of calibrated GUI accuracy. Outer-frame geometry uses the shared evaluator.
Unresolved theme fills and font-family identity are not inferred from the PDF.

The shared evaluator then applies actual Init normalization and graded preservation penalties.
A missing native model fails this episode, not a new deck-wide hard gate. Untargeted supported
SmartArt objects also receive semantic protection. Previously exported task bundles are not
rewritten: rebuild and revalidate a bundle to adopt these contracts.

## Supported boundary and verification

The first implementation accepts connected ordered trees with one document root, at most 199
content nodes, and an unambiguous one-to-one mapping to a readable, flat diagram drawing cache.
It reads both `presAssocID` and `presOf` associations. Cache group transforms, when present, must
be complete. Source labels must be nonempty and agree between data and display. Diagrams
sharing package parts, ambiguous mappings, nested caches, unassociated drawing objects and
unsupported visibility effects or custom/inherited node geometry are rejected. This deliberately
excludes some legitimate layouts.

Automatic red-team checks generate data-only edits, cache-only edits, duplicate cached shapes
and equivalent rebuilt IDs for every SmartArt target. Regression tests additionally cover
partial repair, changed parentage, absent caches, obscuring shapes, split runs, rescaled cache
coordinate units, numerical formatting and native-object loss.

These tests use original synthetic XML fixtures. They do not establish WPS/PowerPoint/LibreOffice
round-trip stability. A real target-editor open/save/render review remains required before
production export. In particular, check that a layout engine retains the intended visible
mutation after opening. Arbitrary branch insertion/deletion, full topology mutation, automatic
layout regeneration, custom-path equivalence and font/layout appearance evaluation remain outside
this implementation.

The underlying data/presentation association model is described in Microsoft's
[DrawingML diagrams API](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.diagrams)
and illustrated by its [Open XML SmartArt sample](https://github.com/OfficeDev/Office-Add-in-samples/blob/main/Samples/word-add-in-load-and-write-open-xml/C%23/LoadingAndWritingOOXMLWeb/OOXMLSamples/SmartArt.xml).
