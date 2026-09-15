# Changelog

## Unreleased

- Three native SmartArt operations: replace/erase a node label, swap two labels, and change
  explicit node RGB fill. Data and drawing-cache mutations are synchronized.
- Ordered-tree correspondence, node cardinality, normalized geometry and visible-style scoring;
  new IDs and split text runs are accepted. Unsupported models fail planning with a reason.
- Per-target data-only/cache-only, duplicate-drawing and equivalent-ID red-team variants.
- SmartArt snapshots are included in agent proposals, protected contracts and desktop runtimes.
- This is bounded support, not arbitrary SmartArt layout regeneration or a WPS playback claim.

## 0.7.0

- 15 new registered visual, typography, paragraph and chart-display mutations (33 total).
- Character-aligned formatting evaluation accepts equivalent split runs and new object IDs.
- Embedded chart value mutations synchronize supported XLSX cells and chart caches; cache-only
  repairs fail the affected chart episode rather than the whole task.
- Target and protected objects share one assignment; explicit visual/style collateral damage
  receives graded penalties. New compiled plans use version 1.1.
- `refract capabilities` and complete operation arguments in the design-agent prompt.
- Additional equivalence, partial-repair, invalid-input and adversarial regressions;
  standalone desktop runtime includes all new evaluator dependencies.
- Existing task bundles are not rewritten. Rebuild and revalidate to adopt the new contracts.

## 0.6.2

- Public Alpha documentation with a clear installation, authoring and deployment path.
- Historical evaluator image excerpts, score provenance and explicit calibration limitations.
- FAQ, contribution workflow, structured issue forms and private security reporting guidance.
- No evaluator behavior or task contract changes from 0.6.1.

## 0.6.1

- MIT license and package license metadata.
- CI-gated Alpha releases with wheel, source distribution and checksums.
- User-facing compatibility scope and target-editor acceptance procedure.

## 0.6.0

- Workspace initialization, task preparation and explicit design-agent handoff.
- Readiness diagnostics and resumable workspace batch builds without manual JSONL assembly.
- Optional portable authoring skill using the same CLI and evidence rules.
- README visual guide: lifecycle, verifier separation, and measured demo progress.
- Original reproducible SVG diagrams.

## 0.5.0

- Original-input demo with real 0 / 0.5 / 1 candidate evaluations.
- Isolated optional LibreOffice PDF export, timeout and no-overwrite behavior.
- Production-checked desktop release command; PDF readability and page-count check.
- Concurrent batch builder, stable registry, owner-fenced state and per-task OS file locks.
- Review/batch identities include materials; malformed/stale receipts fail with diagnostics.
- Native table and connector mutation/evaluation contracts and richer agent-design evidence.
- Numeric text formatting is strict; table content keeps cell coordinates; chart categories
  and extra series affect data scoring.
- Desktop adapter packages hidden runtime separately and collects the saved artifact.
- Getting-started guide, mutation parameter reference, evaluation lessons and explicit limits.
- Cross-platform CI matrix and runnable synthetic regression tests.

Task bundles and source corpora are not included. SmartArt and animation scoring are incomplete;
WPS/LibreOffice compatibility requires validation in the deployment environment.
