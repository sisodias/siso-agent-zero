# Agent guide

SISO Agent Zero is a coordination-policy and boot package. Preserve that boundary.

- Keep model hosts, Herdr, Agent Brain, Skills, Playbooks, and Project OS as external contracts.
- Do not add provider credentials, personal endpoints, machine paths, runtime state, or implicit permission bypasses.
- Boot and write-side announcements must remain separately selectable.
- Host execution must remain explicit and shell-free.
- Update `MIGRATION-MAP.json` when a warehouse source is promoted, deferred, or reclassified.
- Run `npm test` before claiming the repository is publishable.
- Keep install and uninstall disposable-root tests passing; uninstall must refuse unmarked or broad targets.
