# Frequently asked questions

## What do I need to start?

Python 3.11 or newer is enough for the original synthetic demo when installed with the
`demo` extra. Real task authoring needs a local PPTX you may use, a matching reference PDF,
and an agent or person to design its proposal. An editor is needed to render real references
and verify saved results. WPS and LibreOffice are not bundled.

## Is REFRACT a dataset, a model, or an agent skill?

It is a Python framework and CLI. The repository includes an optional authoring skill that
guides your agent through the CLI. It does not include a trained model, a source corpus or
the maintainers' generated task collection.

## Does it call a model API automatically?

No. `prepare-task` creates an inventory, design prompt and `HANDOFF.md`. Supply those files
to your own agent and have it write `proposal.json`. The factory then validates and executes
the proposal deterministically. Credentials and model-provider choices stay in your workflow.

## Can it generate the reference PDF?

Yes, through an optional local LibreOffice installation. Omit `--reference` when preparing a
task, or use `refract render-pdf`. For WPS-specific fidelity, export the PDF from the same
WPS/font environment used for rollouts and pass it explicitly. A reference must show the
intended completed deck; a valid page count alone does not establish visual fidelity.

## Can the solving agent use code?

Yes. The evaluator scores the final editable artifact, not the editing method. Your runner
controls the tools exposed to the agent. Equivalent rebuilt objects should be accepted within
the supported contracts; screenshot substitution is not equivalent to a native editable object.

## What does passing validation mean?

It means the configured checks and evidence requirements passed for that task and evaluator
revision. It does not guarantee a specific model score, rollout length, absence of all hacks
or compatibility with every editor. Run representative canaries before scaling. See
[production validation](production.md) and [compatibility](compatibility.md).

## Are the historical demonstration scores reproducible from this repository?

The selected image excerpts document earlier calibration work. Their underlying private
candidate files and runtime revision are not distributed, and some contracts are not migrated.
The included `refract demo` is the separate executable example for the current release.
See [evidence and provenance](empirical-evidence.md).

## Where should I put generated files?

Keep source corpora, task bundles, credentials and private rollout traces outside version
control. Workspace commands create local task directories and resumable run state. Deployment
separates public inputs from verifier-only artifacts; do not give a solving agent the whole
authoring bundle. See [runner integration](runner-adapters.md).
