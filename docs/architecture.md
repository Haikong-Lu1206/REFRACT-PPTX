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
directory renamed to the requested output. The builder also proves complete source-object
coverage, positive reward for every isolated honest repair, slide-reorder hard-gate behavior,
and graded protected-object damage. Failed builds remove staging output.

## Batch control plane

`batch-build` consumes JSONL records that point to local presentations, references, materials,
and agent-authored declarative proposals. A SQLite WAL state store records leased stage claims,
attempts, failures, and reusable outputs. Expired worker leases can be reclaimed. A separate
transactional registry assigns stable IDs from source and design content, so reruns do not
renumber tasks and duplicate logical records are rejected before workers start.

Completed receipts are not trusted blindly: the batch runner revalidates the declared bundle
and deployment before reuse. Missing artifacts are rebuilt; invalid existing artifacts are not
silently overwritten.

## Data boundary

Source decks, reference renders, materials, generated tasks, and candidates do not belong in
the code repository. They are addressed by hashes from a separate artifact store. This makes
the repository safe to publish and keeps corpus licensing auditable.

## Deployment adapters

Validated bundles remain independent of any desktop runner. A runner adapter compiles a bundle
into target-specific task code, public assets, hidden evaluator assets, and a hash-pinned
deployment manifest. The adapter may add setup and result-collection behavior, but it cannot
change the compiled mutation plan or scoring semantics.

The built-in desktop adapter produces a `BaseTask` subclass while keeping reference renders and
materials separate from the evaluator plan and frozen initial inventory. Its evaluator runtime
is packaged with the task, so runner upgrades do not silently change task scores. Publication is
a second transaction: public assets must be reachable and byte-verified before runner files are
staged.

## Production gate

The strict production gate binds all receipts to a hash of the current bundle. It requires a
known source license, deterministic build and red-team success, a blind review performed only
from agent-visible evidence, and a real-office roundtrip with an oracle-quality baseline and
bounded score loss. Policies are versioned JSON and can relax gates for development without
changing the default publication contract.
