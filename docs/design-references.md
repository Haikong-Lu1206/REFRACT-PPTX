# Authoring patterns adopted by REFRACT

This comparison concerns usability and architecture, not model rankings. The projects below
are useful references for task authoring and evaluation; REFRACT does not claim their adapters
or dataset formats are supported.

| Primary reference | Useful pattern | Concrete REFRACT behavior |
|---|---|---|
| [Harbor task structure](https://www.harborframework.com/docs/tasks) | Initialize a predictable task directory; offer an authoring skill | `init-workspace`, `prepare-task`, and `skills/refract-task-author` |
| [Harbor core concepts](https://www.harborframework.com/docs/core-concepts) | Treat tasks, agents and environments as separate concepts | Proposal/task bundle separate from runner profile and deployment |
| [Verifiers overview](https://github.com/PrimeIntellect-ai/verifiers/blob/main/docs/overview.md) | Separate reusable tasks, execution harnesses and traces | Authoring inputs, deterministic evaluator and external rollout harness remain separate |
| [Terminal-Bench repository](https://github.com/harbor-framework/terminal-bench) | Validate reference solutions in the execution environment | Require target-editor evidence before production release, beyond init/oracle self-checks |

REFRACT adds presentation-specific constraints: preserve editable native objects, derive targets
from visible reference evidence, measure progress from the damaged init, and verify equivalent
solutions without using original shape IDs as the sole runtime identity.

The authoring skill orchestrates the framework; it does not replace the evaluator. A successful
local build is a candidate task, not evidence of rollout difficulty or universal editor tolerance.
Users still supply their model workflow, authorized sources and real target-editor validation.
