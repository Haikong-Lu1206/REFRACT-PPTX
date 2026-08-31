# Contributing

REFRACT accepts changes to its framework, schemas, validators, and synthetic fixtures.

Before opening a pull request:

1. Run `pytest` and `ruff check .`.
2. Add tests for contract or scoring changes.
3. Use only synthetic, redistributable fixtures created for this repository.
4. Do not commit source presentations, generated tasks, reference renders, or private traces.
5. Document any evaluator tolerance change with both honest-repair and adversarial examples.

New task families or mutation types must include:

- an observable-evidence contract;
- a deterministic mutation contract;
- a partial-credit evaluator contract;
- preservation rules;
- at least one honest partial repair and one attack variant;
- a schema version and migration note.

