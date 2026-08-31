# Architecture

REFRACT separates agent judgment from deterministic execution.

## Control plane

The control plane owns source manifests, stage state, task specifications, validation receipts,
and reports. Stages communicate through versioned JSON artifacts instead of shared process
memory. A stage can therefore be retried without repeating completed work.

## Presentation plane

The presentation plane parses the PPTX package, renders evidence, records native-object
inventories, applies controlled mutations, and evaluates a candidate presentation. Office
applications are treated as external renderers and roundtrip systems, not as the source of
truth for task definitions.

## Agent boundary

The agent may propose scoring points and mutations, but cannot inject executable evaluator
code. Its output is validated against the `TaskSpec` schema. Only registered family plugins
can compile a proposal into mutation and evaluation behavior.

## Family plugins

Every family plugin exposes:

```text
analyze(inventory) -> candidate capabilities
validate_episode(episode) -> validation findings
```

Production plugins additionally provide deterministic mutation, evaluation, attack generation,
and roundtrip validation. Registration is refused until the complete contract is available.

## Data boundary

Source decks, reference renders, materials, generated tasks, and candidates do not belong in
the code repository. They are addressed by hashes from a separate artifact store. This makes
the repository safe to publish and keeps corpus licensing auditable.

