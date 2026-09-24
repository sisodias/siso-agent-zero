# Agent Zero Voice integration seam

This package implements the safe first slice of Agent Zero's voice-to-stack coordination. It converts an already-transcribed, normalized voice request into typed contracts, evaluates confirmation and risk policy, resolves a laptop-Herdr target from replay data, and emits a non-mutating receipt.

It deliberately does **not** listen to audio, call the current voice runtime, contact Herdr, dispatch an agent, write task state, or load credentials.

## Enabled now

- Typed `VoiceIntent`, `TargetBinding`, `ActionReceipt`, and `TaskHandoff` contracts.
- Risk tiers and confirmation gates that fail closed.
- Fixture-only laptop-Herdr target resolution and pre-submit verification.
- In-process idempotency for duplicate request IDs and duplicate semantic actions.
- Plan-only admission for bounded MiniMax read/bulk work.
- Independent-verifier and artifact-evidence gates before coordinator synthesis.
- Replay tests for known routing and submission failures.

## Not enabled

- Live read-only Herdr discovery.
- Message submission to any Herdr pane.
- MiniMax worker dispatch.
- Writes to the existing task manager.
- Voice runtime or Oracle Streaming integration.
- Durable idempotency storage.

See [STAGED-INTEGRATION.md](STAGED-INTEGRATION.md) for the approval gates and wiring order.

## Local references

- [Decision-ready architecture research](../../research/agent-zero-voice-stack-20260724.html)
- [Current Herdr operating conventions](../../templates/profile/skills/herdr/SKILL.md)
- [Existing task-management lane](../../templates/profile/skills/task/SKILL.md)
- [Model-routing conventions](../../templates/profile/skills/model-routing/SKILL.md)
- [Current voice runtime boundary (reference only; never imported)](../voice/voiced.py)

## Test

From the repository root:

```bash
python3 -m unittest discover -s extensions/agent-zero-voice/tests -v
```
