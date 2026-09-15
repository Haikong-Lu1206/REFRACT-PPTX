REFRACT is an Alpha framework for authoring editable presentation repair tasks.

This release includes a local authoring workspace, per-deck agent handoff, deterministic
mutation and scoring, resumable batch generation, an optional authoring skill and a desktop
runner adapter. Source archives and Python wheels are attached with SHA-256 checksums.

Install the wheel with `python -m pip install PATH_TO_WHEEL`. For the original demo, install
its optional dependencies: `python -m pip install "PATH_TO_WHEEL[demo]"`.
The source archive also includes the authoring skill, documentation and diagram generator.

GitHub publication is gated on the Windows/Linux Python test matrix and package checks.
These checks cover synthetic fixtures; they do not establish WPS or LibreOffice compatibility.
Real target-editor acceptance remains unverified for this release. Run a small representative
canary in your deployment environment before scaling.

SmartArt, animation, Morph, recursive group topology and detailed text styling do not yet have
complete scoring contracts. See `docs/compatibility.md` and `docs/task-design.md` for scope.

Framework code and original documentation are provided under the MIT License. Input presentations
and their assets remain subject to their own licenses. This release does not upload to PyPI.
