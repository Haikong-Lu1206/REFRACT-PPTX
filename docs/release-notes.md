## REFRACT 0.7.0 — Expanded repair contracts (Alpha)

REFRACT is a framework for authoring editable presentation repair tasks, informed by real
model rollouts and iterative task/evaluator development.

This release includes a local authoring workspace, per-deck agent handoff, deterministic
mutation and scoring, resumable batch generation, an optional authoring skill and a desktop
runner adapter. Source archives and Python wheels are attached with SHA-256 checksums.

This update adds 15 mutations (33 total): picture rotation/flip/crop, shape presets and lines,
explicit text size/color/emphasis, paragraph alignment/bullets/indentation, and chart display
properties. Character-aligned styles accept equivalent split runs. Supported chart values and
their embedded XLSX cells are updated together; cache-only repairs fail that chart episode.
Run `refract capabilities` for operation arguments and scoring components.

New compiled plans use version 1.1. Target/protected objects share one assignment and recorded
visual/style collateral damage receives graded penalties. Scores may change relative to older
evaluators. Existing bundles are not rewritten: rebuild and revalidate to adopt these contracts.

Install the wheel with `python -m pip install PATH_TO_WHEEL`. For the original demo, install
its optional dependencies: `python -m pip install "PATH_TO_WHEEL[demo]"`.
The source archive also includes the authoring skill, documentation and diagram generator.

GitHub publication is gated on the Windows/Linux Python test matrix and package checks.
These checks cover synthetic fixtures; they do not establish WPS or LibreOffice compatibility.
Real target-editor acceptance remains unverified for this release. Run a small representative
canary in your deployment environment before scaling.

SmartArt, animation, Morph, recursive group topology and inherited text styling do not yet have
complete scoring contracts. Read the
[getting-started guide](https://github.com/Haikong-Lu1206/REFRACT-PPTX/blob/v0.7.0/docs/getting-started.md),
[compatibility requirements](https://github.com/Haikong-Lu1206/REFRACT-PPTX/blob/v0.7.0/docs/compatibility.md)
and [capability matrix](https://github.com/Haikong-Lu1206/REFRACT-PPTX/blob/v0.7.0/docs/capabilities.md).

Framework code and original documentation are provided under the MIT License. Input presentations
and their assets remain subject to their own licenses. This release does not upload to PyPI.
