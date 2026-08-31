# REFRACT

**Reference-guided Evaluation Framework for Reconstruction and Agent-designed Controlled Transformations**

REFRACT is an agent-guided factory for mining real presentations, designing controlled
failures, and building robust reconstruction tasks. It combines presentation-specific
reasoning with deterministic mutation, evaluation, and adversarial validation.

The repository contains the framework, contracts, and synthetic examples. It does **not**
ship generated tasks, source corpora, presentation assets, or private evaluation data.

## Why REFRACT

Randomly deleting a shape is easy to automate, but it rarely produces a meaningful task.
REFRACT separates the work into two parts:

1. An agent studies each deck and proposes mutations that are visible, recoverable, and
   specific to the presentation's structure.
2. Deterministic code validates the proposal, applies the mutation, compiles the evaluator,
   and tests partial credit and attack resistance.

This keeps creative task design where judgment is useful while making generation,
validation, and scoring reproducible.

## Task families

- **Reference reconstruction** repairs mixed damage using a rendered reference and supplied
  materials while preserving editability.
- **Spatial structure repair** restores geometry, z-order, overlap, connectors, arrows, and
  cross-slide spatial relationships.
- **Native chart repair** restores chart data and native chart semantics together with the
  surrounding layout.

Internally, every family implements the same analysis and validation contract. New mutation
types must provide a planner contract, deterministic mutator, evaluator, and adversarial test
variants before they can be registered.

## Pipeline

```text
Discover -> Screen -> Inspect -> Design -> Compile -> Mutate
         -> Evaluate -> Red-team -> Validate -> Bundle -> Report
```

- **Discover** records source, license, hashes, and crawl provenance.
- **Screen** removes corrupt, duplicate, uneditable, or structurally weak decks.
- **Inspect** builds a package-level inventory of slides and native objects.
- **Design** asks an agent for deck-specific scoring points and mutations.
- **Compile** turns the proposal into a versioned declarative task specification.
- **Validate** checks solvability, score monotonicity, preservation, editor roundtrips, and
  known attack strategies.

See [Architecture](docs/architecture.md) and [Task contracts](docs/task-contract.md).

## Quick start

REFRACT requires Python 3.11 or newer and has no mandatory runtime dependencies.

```bash
python -m pip install -e ".[dev]"
refract doctor
refract inspect path/to/deck.pptx
refract discover path/to/corpus --output corpus.jsonl
refract screen path/to/corpus --output screening.jsonl
refract validate-spec examples/synthetic_demo/task_spec.json
```

Generate a standalone HTML summary from an inventory or screening JSON/JSONL file:

```bash
refract report screening.jsonl --output report.html
```

## Repository boundary

Large files and generated task bundles are deliberately excluded from Git. A production
deployment should store them in a separate versioned object store and reference them through
content hashes. The framework treats publishing as a separate, auditable transaction.

## Status

REFRACT is an early public release. The current CLI provides corpus discovery, package-level
PPTX inspection, mechanical screening, family routing, task-spec validation, bundle checks,
and HTML reports. Mutation and evaluator implementations are being migrated behind the
public family contracts and will be released only after parity and adversarial tests pass.

## Development

```bash
pytest
ruff check .
```

Contributions should not include presentation corpora, generated tasks, or material derived
from non-redistributable decks. See [CONTRIBUTING.md](CONTRIBUTING.md).

