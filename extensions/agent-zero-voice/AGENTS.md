# Agent Zero Voice Package Rules

This package is an offline integration seam for Agent Zero voice coordination. It is not a voice runtime and it is not a second task system.

## Hard boundaries

- Keep `dry_run=True` mandatory until the approvals in `STAGED-INTEGRATION.md` are recorded.
- Do not import or call `extensions/voice/voiced.py`, Herdr CLI/process transports, Oracle Streaming, credentials, sockets, or live agent APIs.
- Do not add a task database. `TASK-*` remains the join key into the existing task-management lane.
- Fixture/replay data is the only permitted source for laptop-Herdr discovery in this package.
- MiniMax workers are plan-only here. They cannot self-fan-out, write live systems, share output paths, or make the final decision.
- Every mutating capability must remain fail-closed and require a new reviewed stage plus explicit approval.

## Source of truth and checks

- Executable contracts: `agent_zero_voice/contracts.py`
- JSON interface contracts: `contracts/*.schema.json`
- Risk/confirmation policy: `agent_zero_voice/policy.py`
- Staged approvals: `STAGED-INTEGRATION.md`
- Replay evidence: `tests/fixtures/`
- Run: `python3 -m unittest discover -s extensions/agent-zero-voice/tests -v`

When behavior changes, update the executable contract, its JSON schema where applicable, replay fixture, test, and staged document together.
