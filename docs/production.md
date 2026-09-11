# Production workflow

Use one JSON object per line in a batch manifest. Every record requires `key`, `presentation`,
`reference`, `proposal`, `source_uri`, and `license`; `materials` and an explicit `task_id` are
optional. Relative paths are resolved from the manifest directory.

```bash
refract batch-build batch.jsonl --output run --workers 8
```

The output contains:

```text
run/
  bundles/<stable-task-id>/
  deployments/<stable-task-id>/     # when --profile is supplied
  run-state.sqlite
  task-registry.sqlite
```

The state database is safe for concurrent processes. A worker receives a lease rather than an
unbounded `running` flag. Re-running the command reuses only a complete, still-valid artifact.
Failures remain visible in `refract run-status` and can be retried by running the same manifest.

Each claim has a distinct owner token. A live lease blocks competing inputs too; after reclamation,
the previous worker cannot complete, fail, or heartbeat the replacement worker's record. Resetting
a receipt only removes completed work, never a running claim. Batch leases last four hours; there
is currently no automatic heartbeat thread, so do not run an individual build longer than that.
Per-task OS locks also protect bundle/deployment writes across workers, even when manifest keys
differ. Locks are released by the OS when a worker exits. Use local storage with working OS file
locks and SQLite locking; network filesystem semantics are not certified.

Completed batch receipts also bind the bundle content, including every material's relative path
and hash. A modified completed bundle is reported as failed rather than silently reused. Inspect
that change and use a fresh output/state location when intentionally rebuilding.

## Required receipts

`build-task` creates `validation/build.json` and `validation/redteam.json`. Red-team validation
checks source-object coverage, each isolated honest repair, slide reorder, and protected-object
damage. It stores scores and gate results, not the temporary attack decks.

A release reviewer then uses only `instruction.md`, `init.pptx`, `reference.pdf`, and
`materials/` and records the decision with `record-blind-review`. After an oracle-quality deck
is opened and saved by the target office suite, use `record-office-roundtrip` with the before and
after files. `validate-production` rejects missing, failed, or stale receipts.

The example policy in `configs/production-policy.example.json` is strict by default. Development
can use a separate policy, but changing a policy never mutates evaluator semantics or an existing
bundle.

Review identities include materials. Adding, removing, renaming, or modifying a material invalidates
prior blind-review and office receipts. Malformed receipts, non-finite scores, missing catastrophic
gates, and inconsistent before/after score losses are rejected with diagnostics.

Office receipts record externally supplied before/after files; this command does not launch WPS or
prove a real editor session occurred. Synthetic tests of receipt validation are not Office
compatibility evidence. Run the target editor independently before recording production evidence.
Use `release-desktop` to enforce production checks before export. `emit-desktop` and batch profile
exports remain development commands and do not imply production approval. The strict release
check also requires a readable unencrypted PDF with one page per slide.
