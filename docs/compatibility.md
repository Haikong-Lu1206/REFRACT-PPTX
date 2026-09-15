# Compatibility and validation

REFRACT is an Alpha release. Choose tasks within the implemented contracts and validate them
in the editor and runner image you intend to deploy.

| Layer | Validation available | Limit |
|---|---|---|
| Python core | Synthetic mutation, scoring, batch and adapter tests | Synthetic files are not an Office compatibility suite |
| Packaging | Wheel smoke test; release workflow checks wheel and source distributions | Model clients and Office are not bundled |
| Windows/Linux | CI targets Python 3.11 and 3.13 | Check the specific commit's Actions results |
| PDF export | Optional isolated LibreOffice process with timeout | Fonts and output layout depend on the installed editor |
| WPS end-to-end | No published real-editor acceptance result for this release | Required in the target rollout image before scaling |
| Editor roundtrip receipts | Before/after files scored by the evaluator | Operator-supplied evidence; not proof the editor was run |

## Target-editor acceptance

Use at least three original or licensed decks that collectively include text/layout, native
tables/charts, and pictures/connectors. Include a large legitimate image if your pool uses one.

For each deck:

1. Build the task and record its version and bundle identity.
2. Deploy with the actual profile and check asset downloads, paths and setup.
3. Open an oracle-quality answer in the target editor, save, close, reopen, and inspect target pages.
4. Score the saved file through the runner's final-file collector, including with WPS closed.
5. Submit an untouched init and a genuinely partial repair; confirm useful intermediate scores.
6. Record suite/version, operating system, fonts, before/after hashes, component scores, visual
   findings, and infrastructure exceptions. Do not record an environment failure as agent zero.

`record-office-roundtrip` and `release-desktop` support this process. A failed check requires
investigation; do not loosen the policy solely to obtain a passing release.

## Scoring limitations

Picture signatures are not proof of asset provenance. Chart workbook/cache synchronization,
theme resolution, recursive groups and exact rendered occlusion are not fully covered.
SmartArt, formulas, animations, Morph and detailed typography need additional contracts before
they can be advertised as evaluated capabilities. Current reference and preservation rules
should not be interpreted as a full rendering-equivalence test.
