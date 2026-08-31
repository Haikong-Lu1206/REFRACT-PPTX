# REFRACT

**Reference-guided Evaluation Framework for Reconstruction and Agent-designed Controlled Transformations**

REFRACT is an agent-guided factory for mining real presentations, designing controlled
failures, and building robust reconstruction tasks. It combines presentation-specific
reasoning with deterministic OOXML mutation, normalized evaluation, and adversarial gates.

The repository contains the framework, contracts, and synthetic examples. It does **not**
ship generated tasks, source corpora, presentation assets, or private evaluation data.

## Why REFRACT

Randomly deleting a shape is easy to automate, but it rarely produces a meaningful task.
REFRACT separates the work into two parts:

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

Tasks may combine these families. Internally, each mutation remains routed through one
registered family, so mixed tasks do not introduce hidden task-specific evaluator code.

## Pipeline

```text
Discover -> Screen -> Inspect -> Design -> Compile -> Mutate
         -> Evaluate -> Red-team -> Validate -> Bundle -> Report
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

Score an output deck against the generated init and hidden compiled plan:

```bash
refract evaluate candidate.pptx bundles/example-repair-task/init.pptx \
  bundles/example-repair-task/evaluator/plan.json
```

Generate a standalone HTML summary from an inventory or screening JSON/JSONL file:

```bash
refract report screening.jsonl --output report.html
```

## Repository boundary

Large files and generated task bundles are deliberately excluded from Git. A production
deployment should store them in a separate versioned object store and reference them through
content hashes. The framework treats publishing as a separate, auditable transaction.

## Implemented evaluator behavior

- geometry has a full-credit region and continuous falloff rather than exact-coordinate cliffs;
- target matching is maximum-weight one-to-one assignment, including both ends of a swap;
- picture identity uses SHA-256 as a fast path and a 12x12 visual signature after re-encoding;
- native charts support cached values, title/legend presence, and series-color scoring;
- untargeted visible objects carry graded preservation contracts;
- slide count, slide order, slide size, and unauthorized full-page pictures are hard gates;
- large-image penalties begin continuously at 40% coverage and hard-zero at 80% unless a
  strongly matched expected picture has the correct geometry.

See [Evaluation](docs/evaluation.md) for the exact current contract.

## Current boundary

The executable core currently covers registered shape, picture, spatial, text/fill, and native
chart operations. Native table cell semantics, SmartArt topology, connector attachment IDs,
animations, transitions, rendering, and real-office roundtrip automation are not yet registered
mutation/evaluator plugins. The bundle receipt proves package-level `Init=0` and `Oracle=1`; a
production deployment should add its own renderer and office-suite roundtrip receipts before
publishing tasks from those future capabilities.

## Development

```bash
pytest
ruff check .
```

Contributions should not include presentation corpora, generated tasks, or material derived
from non-redistributable decks. See [CONTRIBUTING.md](CONTRIBUTING.md).
