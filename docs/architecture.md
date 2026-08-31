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
code, XPath, or package paths. Its JSON is validated against the `AgentProposal` contract,
then resolved against an inventory. Only registered operations can enter a compiled plan.

The public package deliberately does not choose a model provider. `proposal-prompt` emits the
text contract and evidence inventory; a deployment attaches its reference render and materials
to the provider of its choice, then returns declarative JSON to `compile-proposal`.

## Family plugins

Every family plugin exposes:

```text
analyze(inventory) -> candidate capabilities
validate_episode(episode) -> validation findings
```

The current registry exposes family capabilities while mutation and evaluation are dispatched
through a shared, versioned OOXML operation catalog. A new operation is incomplete until it has
proposal validation, deterministic mutation, component scoring, and honest/adversarial tests.

## Atomic build

`build-task` writes into a unique sibling staging directory. It compiles the plan, creates the
init, extracts any deleted picture material under an anonymous hash name, checks `Init=0` and
`Oracle=1`, writes validation receipts, and runs bundle validation. Only then is the staging
directory renamed to the requested output. Failed builds remove staging output.

## Data boundary

Source decks, reference renders, materials, generated tasks, and candidates do not belong in
the code repository. They are addressed by hashes from a separate artifact store. This makes
the repository safe to publish and keeps corpus licensing auditable.
