# From installation to your first batch

For the shortest real-task path, use `init-workspace`, `prepare-task`, `workspace-status`, and
`build-workspace` as shown in the README. The detailed commands below remain available for
custom pipelines. The optional [authoring skill](../skills/refract-task-author/SKILL.md) can
guide your own agent through either path.

## 1. Run a complete local example

Use Python 3.11 or newer in a virtual environment. From the repository root:

```bash
python -m pip install -e ".[demo]"
refract doctor
refract demo --output runs/first-demo
```

This creates two original slides, a matching authored PDF, a declarative proposal, a built
task bundle, and a real partially repaired PPTX. `scores.json` should report **0 / 0.5 / 1**.
Open the source, init, and one-title-repaired decks to inspect the changes. This example tests
the software path; it is intentionally simple and is not a recommended training difficulty.
Choose a new output directory to rerun; REFRACT refuses to overwrite your work.

The demo PDF uses equivalent basic text drawing, not a WPS rendering. For real tasks export
the source from the target editor, or use the optional command below with LibreOffice installed:

```bash
refract render-pdf my-source.pptx --output my-reference.pdf
```

No office program is needed for the synthetic demo. Rendering real decks does require an
installed editor. Use the same editor/fonts as your rollout when visual fidelity matters.

## 2. Bring a deck you may use

```bash
refract discover my-corpus --license CC-BY-4.0 --output runs/corpus.jsonl
refract screen my-corpus --output runs/screening.jsonl
refract report runs/screening.jsonl --output runs/screening.html
refract inventory-objects my-source.pptx --output runs/objects.json
refract proposal-prompt my-source.pptx --output runs/design-prompt.txt
```

`--license` records your declaration; it does not infer permission. Inspect screening results:
a structural quality score is a shortlist, not a guarantee of interesting or solvable tasks.

## 3. Ask your design agent for a proposal

Give your agent `design-prompt.txt`, the source/reference, and relevant materials. The command
does not attach PDF pages to a model or make an API call. Attach them in your own agent workflow.
Save its JSON response as `proposal.json`. The generated prompt contains the schema, available
capabilities, concrete object structures, operations, and compatible scoring components.

The reference must show every intended correction. Choose mutations based on what is distinctive
in this deck, not a random sample of supported operations. Use `runs/first-demo/proposal.json`
as a syntax example, not a template to repeat across a corpus. See [design guidance](task-design.md).

```bash
refract compile-proposal my-source.pptx proposal.json --output runs/plan.json
refract build-task my-source.pptx proposal.json --reference my-reference.pdf --task-id my-task --source-uri local://my-deck --license CC-BY-4.0 --output bundles/my-task
```

Build rejects unresolved targets, unsupported mutations, nonzero init, imperfect oracle, and
failed built-in red-team checks. The bundle includes public inputs and hidden evaluator state;
do not expose the whole bundle to a solving agent.

## 4. Scale approved designs

Create JSONL records in the format of `examples/batch-manifest.example.jsonl`, using actual paths
and one agent-designed proposal per record. Paths are relative to the manifest, not your shell.

```bash
refract batch-build batch.jsonl --output runs/batch --workers 4 --result runs/batch/result.json
refract run-status runs/batch/run-state.sqlite
```

Rerun the same command to resume. Complete unchanged bundles are reused, errors are recorded,
and running workers are not treated as successful completion. IDs identify the source, design,
materials, framework version and adapter profile. Changing those inputs intentionally creates
a new identity; do not force the old requested ID onto a revised task.

## 5. Validate and deploy

Perform blind review using only the solver-visible files. Open and save an oracle-quality
answer in the target editor and record the real before/after pair:

```bash
refract record-blind-review bundles/my-task --reviewer reviewer-name --decision pass
refract record-office-roundtrip bundles/my-task oracle-before.pptx oracle-after.pptx --office-suite "Target editor and version"
refract release-desktop bundles/my-task --profile configs/desktop-runner.example.json --output runs/deployment
```

Edit the example profile's asset URL, desktop path, application command and runner import first.
`release-desktop` enforces production validation; `emit-desktop` is for development exports.
Publish only public assets and install only runner/hidden files in the evaluator environment.
See [runner adapters](runner-adapters.md) for the actual BaseTask interface and asset commands.

Start with a few tasks containing different object types. Test download, setup, save/close,
final-file collection, and scoring inside the actual rollout image before a large batch.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `refract` command missing | Activate the environment used by pip; alternatively run `python -m refract_pptx`. |
| Office executable missing | Export PDF manually or supply `--office-executable`; core scoring needs no Office. |
| Proposal rejected | Use only the printed catalog and compatible scoring keys; inspect target slide/kind/ID. |
| Oracle below 1 | Stop that task; inspect component scores and native object representation before scaling. |
| Production review stale | Inputs/materials changed; repeat review on the new revision. |
| Office score drops | Compare native structures and rendering; do not register the damaged output as acceptable. |
| Batch entry remains running | Another worker owns it; check the process before restarting. Expired leases are reclaimed. |
| Saved output missing | Check the configured desktop and filename, plus the generated instruction paths. |
