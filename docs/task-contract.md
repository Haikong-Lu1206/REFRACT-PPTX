# Task contract

A REFRACT task is represented by a versioned, declarative `TaskSpec`. The specification records
what evidence a solver can observe, what must be repaired, how success is measured, and which
untargeted content must be preserved.

## Evidence tiers

- `reference_visible`: only properties visibly recoverable from the rendered reference may be
  required.
- `initial_state`: exact properties may be required when they survive in the initial deck.
- `material_grounded`: identity may be required when a supplied material provides it.
- `editor_observable`: native structure may be required when it is visible through ordinary
  presentation editing interfaces.

Hidden ground-truth properties cannot be promoted into mandatory criteria without observable
evidence.

## Episode requirements

Each episode contains:

- stable episode identifier;
- family and capability;
- affected slide numbers;
- mutation description;
- evidence tier and observable evidence;
- evaluator component names and weights;
- acceptance criteria.

Episode weights must be positive and sum to one across a task. Evaluator components within an
episode must also sum to one.

## Validation receipts

Production bundles should carry receipts for:

- initial score and oracle score;
- honest partial repairs;
- protected-object behavior;
- package parse and editor roundtrip;
- attack variants;
- asset provenance and source licensing.

