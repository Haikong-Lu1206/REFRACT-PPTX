# Runner adapters

REFRACT task design is runner-neutral. A runner adapter compiles one validated bundle into the
filesystem layout and Python contract expected by a desktop evaluation harness. It does not
change the mutation plan or evaluator semantics.

## Desktop BaseTask adapter

The built-in `desktop_base_task` adapter targets a harness that dynamically loads a `BaseTask`
subclass and provides `SetupController`, `get_vm_file`, and `get_vm_command_line`. All target-
specific values live in a JSON profile rather than in the task factory.

```bash
refract emit-desktop bundles/example-repair-task \
  --profile configs/desktop-runner.example.json \
  --output deployments/example-repair-task
```

The output deliberately separates trust domains:

```text
deployment.json
public_assets/<task-id>/
  init.pptx
  reference.pdf
  materials/...
task_class/task_<task-id>.py
task_assets/task_<task-id>/
  metadata.json
  tests/assets/
    plan.json
    init_inventory.json
    runtime.zip
```

Only `public_assets/` may be copied to an agent-visible dataset. `task_class/` and
`task_assets/` belong in the runner checkout. The deployment manifest records every file's
role, visibility, hash, remote path, and VM path, so publication does not infer trust from a
filename or directory convention.

## Local or mirrored deployment

Copy public files using the same remote paths embedded in the generated task:

```bash
refract copy-public-assets deployments/example-repair-task /srv/refract-assets
REFRACT_ASSET_BASE=/srv/refract-assets refract verify-public-assets \
  deployments/example-repair-task
```

After assets are reachable, install the runner and hidden evaluator files:

```bash
refract stage-runner deployments/example-repair-task /path/to/runner \
  --asset-base-url /srv/refract-assets
```

Remote verification downloads every public file and compares its SHA-256. Runner files are not
staged until that succeeds. `--skip-asset-verification` exists for offline preparation, but it is
an explicit opt-out and should not be used for a production rollout.

## Runtime behavior

Setup performs these actions:

1. Removes stale task files and materials from the fixed desktop paths.
2. Downloads the initial deck, reference PDF, and every material.
3. Verifies the bytes on the VM against the generated hashes.
4. Writes a setup timestamp, sets the PPTX file association, and launches WPS directly.

Evaluation only forces `Ctrl+S` when the fixed-path file is still byte-identical to the supplied
init. If the file already changed, it is not saved again, because a stale WPS buffer could
overwrite valid disk output. Evaluation then closes office processes, retrieves the fixed-path
file, or recovers exactly one unambiguous Save As result. Multiple possible results are never
best-picked.

The evaluator runtime is a version-pinned ZIP inside hidden assets. The runner does not need a
REFRACT installation, and runtime, plan, and initial inventory hashes are checked before scoring.
Infrastructure failures raise visibly; malformed or absent agent output receives a normal zero
with a diagnostic reason.

## Profile fields

The profile controls asset storage, output layout, desktop paths, application launch command,
snapshot, related applications, and VM volume size. `intermediate_eval_safe` must remain false:
this evaluator closes WPS while persisting and collecting the final file.

`REFRACT_ASSET_BASE` overrides the compiled asset URL at runtime. This supports local mirrors and
air-gapped evaluation without changing or regenerating task modules.
