# Security

Please report evaluator bypasses, provenance weaknesses, archive parsing issues, or accidental
data exposure using [GitHub private vulnerability reporting](https://github.com/Haikong-Lu1206/REFRACT-PPTX/security/advisories/new).
Include the affected version, a minimal synthetic reproduction, expected/actual behavior and
potential impact. Do not include credentials, proprietary decks or private traces. Ordinary
installation and usability bugs belong in the public issue tracker.

Security fixes target the latest Alpha release and the default branch; older Alpha versions
are not maintained separately. There is no guaranteed response-time SLA.

REFRACT treats presentation files as untrusted archives. Production deployments should apply
file-size limits, XML expansion limits, network isolation, and sandboxed rendering.
The Python parser and optional editor integration are not a security sandbox. Keep hidden
evaluation contracts outside the solving agent's accessible filesystem and tools.
