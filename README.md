# REFRACT

**Reference-guided Evaluation Framework for Reconstruction and Agent-designed Controlled Transformations**

REFRACT is an agent-guided factory for mining real presentations, designing controlled
failures, and building robust reconstruction tasks. It combines presentation-specific
reasoning with deterministic OOXML mutation, normalized evaluation, and adversarial gates.

The repository contains the framework, contracts, and synthetic examples. It does **not**
ship generated tasks, source corpora, presentation assets, or private evaluation data.

## Why REFRACT

Randomly deleting a shape is easy to automate, but it rarely produces a meaningful task.
REFRACT separates the work into three parts:

1. An agent studies each deck and proposes mutations that are visible, recoverable, and
   specific to the presentation's structure.
2. Deterministic code validates the proposal, resolves selectors, freezes oracle and protected
   contracts, applies the mutation, and compiles the evaluator.
3. A staged builder proves `Init=0` and `Oracle=1` before atomically publishing a bundle.

This keeps creative task design where judgment is useful while making generation,
validation, and scoring reproducible.

## Task families

- **Reference reconstruction** repairs missing or damaged pictures, text, fills, and geometry
  using a rendered reference and supplied materials while preserving editability.
- **Spatial structure repair** restores geometry, z-order, overlap, connectors, arrows, and
  cross-slide spatial relationships.
- **Native chart repair** restores chart data and native chart semantics together with the
  surrounding layout.
- **Native table repair** restores cell content and fill plus editable row and column
  proportions.
- **Connector repair** is part of spatial repair and checks attached object semantics,
  connection sites, arrowheads, line style, and geometry without requiring stable shape IDs.

Tasks may combine these families. Internally, each mutation remains routed through one
registered family, so mixed tasks do not introduce hidden task-specific evaluator code.

## Pipeline

```text
Discover -> Screen -> Inspect -> Design -> Compile -> Mutate
         -> Evaluate -> Red-team -> Validate -> Bundle -> Adapt -> Publish
```

- **Discover** records source, license, hashes, and crawl provenance.
- **Screen** removes corrupt, duplicate, uneditable, or structurally weak decks.
- **Inspect** builds a package-level inventory of slides and native objects.
- **Design** prepares an evidence-limited prompt for an external agent to propose deck-specific
  scoring points and mutations.
- **Compile** resolves every selector to one object and freezes target and preservation evidence.
- **Mutate** applies only registered deterministic OOXML operations.
- **Evaluate** uses one-to-one object assignment and continuous progress relative to the init.
- **Validate** checks solvability, preservation, package structure, and registered attack gates.

See [Architecture](docs/architecture.md) and [Task contracts](docs/task-contract.md).

## Quick start

For a complete example without a corpus, model API key, or Office installation:

```bash
python -m pip install -e ".[demo]"
refract demo --output runs/first-demo
```

This generates original inputs and three actual candidate states scoring **0, 0.5, and 1**.
It is a smoke test, not a training task. Follow [the end-to-end guide](docs/getting-started.md)
to design your own tasks, generate references, scale a batch and deploy it. Read
[task design and evaluation lessons](docs/task-design.md) before scaling.

REFRACT requires Python 3.11 or newer. Pillow provides deterministic image signatures.

```bash
python -m pip install -e ".[dev]"
refract doctor
refract inspect path/to/deck.pptx
refract inventory-objects path/to/deck.pptx --output objects.json
refract discover path/to/corpus --output corpus.jsonl
refract screen path/to/corpus --output screening.jsonl
refract validate-spec examples/synthetic_demo/task_spec.json
```

Prepare the agent-design prompt, compile its declarative JSON proposal, and build a bundle:

```bash
refract proposal-prompt source.pptx \
  --evidence "reference.pdf is attached page-by-page" \
  --output design-prompt.txt

refract compile-proposal source.pptx proposal.json --output plan.json

refract build-task source.pptx proposal.json \
  --reference reference.pdf \
  --task-id example-repair-task \
  --source-uri https://example.org/source-record \
  --license CC-BY-4.0 \
  --output bundles/example-repair-task
```

Build many independently designed proposals concurrently with stable content-based IDs and
resume-safe state:

```bash
refract batch-build examples/batch-manifest.example.jsonl \
  --output runs/production \
  --workers 8 \
  --profile configs/desktop-runner.example.json \
  --result runs/production/result.json

refract run-status runs/production/run-state.sqlite
```

Score an output deck against the generated init and hidden compiled plan:

```bash
refract evaluate candidate.pptx bundles/example-repair-task/init.pptx \
  bundles/example-repair-task/evaluator/plan.json
```

Adapt the neutral bundle for a desktop `BaseTask` runner:

```bash
refract emit-desktop bundles/example-repair-task \
  --profile configs/desktop-runner.example.json \
  --output deployments/example-repair-task

refract validate-deployment deployments/example-repair-task
refract copy-public-assets deployments/example-repair-task /srv/refract-assets
refract stage-runner deployments/example-repair-task /path/to/runner \
  --asset-base-url /srv/refract-assets
```

Before publication, add evidence-limited review and real-office save/reopen evidence, then run
the strict gate:

```bash
refract record-blind-review bundles/example-repair-task \
  --reviewer reviewer-name --decision pass

refract record-office-roundtrip bundles/example-repair-task \
  oracle-before.pptx oracle-after-wps-save.pptx \
  --office-suite "WPS Presentation 12 on target image"

refract validate-production bundles/example-repair-task \
  --policy configs/production-policy.example.json

refract release-desktop bundles/example-repair-task \
  --profile configs/desktop-runner.example.json \
  --output deployments/approved-task
```

The deployment separates agent-visible assets from hidden evaluator state, verifies every file
by hash, packages a version-pinned evaluator runtime, safely collects the final saved deck, and
does not require REFRACT to be installed in the runner. See
[Runner adapters](docs/runner-adapters.md) and the [Production workflow](docs/production.md).

Generate a standalone HTML summary from an inventory or screening JSON/JSONL file:

```bash
refract report screening.jsonl --output report.html
```

## Repository boundary

Large files and generated task bundles are deliberately excluded from Git. A production
deployment should store them in a separate versioned object store and reference them through
content hashes. The framework treats publishing as a separate, auditable transaction.

The included deployment commands copy or verify artifacts but intentionally do not push to a
specific Git host or dataset provider. Provider authentication and repository policy stay outside
the task factory.

## Finding source presentations

REFRACT intentionally does not crawl or download presentations from third-party repositories.
It operates on local PPTX files that the user has already obtained and is permitted to reuse.

[Zenodo](https://zenodo.org/) can be useful for finding research presentations, but the presence
of a file on Zenodo does not by itself grant permission to modify or redistribute it. Check the
license attached to each record and file, preserve the DOI and attribution, and confirm that the
license permits adaptations and the intended commercial or noncommercial use. Zenodo's
[Terms of Use](https://about.zenodo.org/terms/) state that downloading content does not transfer
its intellectual-property rights. Unknown, custom, `ND`, or otherwise incompatible licenses
should be excluded unless separate permission has been obtained.

## Implemented evaluator behavior

- geometry has a full-credit region and continuous falloff rather than exact-coordinate cliffs;
- target matching is maximum-weight one-to-one assignment, including both ends of a swap;
- picture identity uses SHA-256 as a fast path and a 12x12 visual signature after re-encoding;
- native charts support cached values, title/legend presence, and series-color scoring;
- native tables expose structure, cell content, visible cell style, and relative row/column
  proportions;
- connectors expose semantic start/end targets, connection sites, arrowheads, line style, and
  geometry;
- untargeted visible objects carry graded preservation contracts;
- slide count, slide order, slide size, and unauthorized full-page pictures are hard gates;
- large-image penalties begin continuously at 40% coverage and hard-zero at 80% unless a
  strongly matched expected picture has the correct geometry.

See [Evaluation](docs/evaluation.md) for the exact current contract.

## Current boundary

Version 0.5 is an executable, tested foundation, not a claim that every production capability
has been migrated or every editor is compatible. The release gate checks real-review receipts;
the core test suite does not manufacture real WPS compatibility evidence.

The executable core currently covers registered shape, picture, text/fill, spatial, z-order,
native chart, native table, and connector operations. SmartArt topology, animations,
transitions, and an office-specific automation driver are not yet registered mutation plugins.
Real-office evidence can already be recorded and enforced after an external WPS or LibreOffice
save/reopen run. Unsupported native families are not advertised to the design agent and cannot
pass the production gate.

## Development

```bash
pytest
ruff check .
```

Contributions should not include presentation corpora, generated tasks, or material derived
from non-redistributable decks. See [CONTRIBUTING.md](CONTRIBUTING.md).
