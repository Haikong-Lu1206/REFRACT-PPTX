# Contributing

REFRACT accepts changes to its framework, schemas, validators, and synthetic fixtures.

## Development setup

Use Python 3.11 or newer and a virtual environment:

```bash
git clone https://github.com/Haikong-Lu1206/REFRACT-PPTX.git
cd REFRACT-PPTX
python -m pip install -e ".[dev]"
python -m pytest
ruff check .
```

Open an issue before introducing a new evaluator family or changing the public contract.
Small bug fixes and documentation improvements can go directly to a pull request. Describe
the observed problem, the resulting behavior and how it was verified. Keep unrelated changes
in separate pull requests.

## Review requirements

Before opening a pull request:

1. Run `pytest` and `ruff check .`.
2. Add tests for contract or scoring changes.
3. Use only synthetic, redistributable fixtures created for this repository.
4. Do not commit source presentations, generated tasks, reference renders, or private traces.
5. Document any evaluator tolerance change with both honest-repair and adversarial examples.

Never commit `auth.json`, API keys, access tokens, service-account credentials or local agent
configuration. Ignore rules are only a safeguard: inspect the staged diff before committing.
If a secret is exposed, revoke it immediately and report the incident privately; deleting the
latest copy alone does not remove it from Git history.

New task families or mutation types must include:

- an observable-evidence contract;
- a deterministic mutation contract;
- a partial-credit evaluator contract;
- preservation rules;
- at least one honest partial repair and one attack variant;
- a schema version and migration note.

For scoring changes, report component scores for Init, Oracle, a legitimate partial repair,
an equivalent reconstruction and a relevant adversarial candidate. Explain any score changes
for existing contracts; do not tune weights solely to make a demonstration look better.

## Where help is most useful

- Target-editor acceptance evidence with explicit WPS/LibreOffice and font versions.
- Small synthetic regressions for save/reopen equivalence and unfair scoring.
- Complete contracts for new native objects, including honest and adversarial examples.
- Clearer setup diagnostics and documentation based on a fresh installation.

See [compatibility](docs/compatibility.md) for current limits. Changes are reviewed by the
maintainers; this Alpha does not promise stable contracts or a fixed release schedule.
