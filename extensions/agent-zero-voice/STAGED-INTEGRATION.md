# Agent Zero Voice staged integration

Status labels in this document are explicit: **FACT** describes code or conventions present in the repository; **RECOMMENDATION** describes a future choice; **APPROVAL REQUIRED** is a capability boundary that this package must not cross by itself.

## Current boundary — Stage 0 plus Stage 1 replay

**FACT:** `agent_zero_voice` accepts structured data after transcription. It has no audio, Oracle Streaming, or voice-runtime integration.

**FACT:** laptop-Herdr target discovery uses a JSON fixture/replay registry only. `FixtureHerdrAdapter.send_live()` always raises `LiveTransportDisabled`.

**FACT:** all accepted actions produce receipts describing what *would* happen. No task, terminal, pane, worker, or external system is mutated.

**FACT:** the package recognizes existing `TASK-*` identifiers and emits `TaskHandoff` contracts. It does not own task state and does not create a competing task database.

**FACT:** MiniMax fan-out is admitted as a plan only. Each slice must be independent, read-only, bounded, have a unique repository-relative output below `research/agent-zero-voice-runs/<TASK-ID>/`, and forbid self-fan-out, live-system mutation, and final-decision authority.

## Operating contract

1. The upstream voice lane performs audio, transcription, and intent extraction.
2. Agent Zero receives one `VoiceIntent` with a request ID, transcript digest, `TASK-*` join key where applicable, confirmation state, constraints, and an exact target hint.
3. `VoiceActionPolicy` computes the minimum risk tier and confirmation level. Understated risk, missing confirmation, and all tier-3 actions fail closed.
4. Idempotency checks both request identity and a canonical semantic-action fingerprint. A duplicate emits `DUPLICATE`; the coordinator does not repeat the action.
5. For an existing-agent action, the fixture adapter resolves workspace, tab, registered pane, role marker, task marker, foreground CWD, and freshness. A remembered pane ID is only a hint.
6. Immediately before a hypothetical submit, the adapter revalidates the binding and blocks a non-empty real composer or changed identity.
7. The coordinator emits an `ActionReceipt` with policy, target, evidence, and dry-run verdict.
8. Work completion is accepted only through a `TaskHandoff`. `PASS` requires an output artifact and digest, successful checks with evidence, and a distinct independent verifier.

## MiniMax bounded-parallel path

**RECOMMENDATION:** reserve MiniMax for independent read-heavy or bulk-transform slices where parallelism materially reduces elapsed time. The coordinator remains responsible for decomposition, admission, dispatch approval, aggregation, synthesis, and the final decision.

Admission rules enforced now:

- Two to five slices; default operational fan-out should remain four or fewer.
- Each slice has a clear objective, bounded input paths, and a dedicated output path.
- No output-path collision and no slice may consume another worker's output.
- Read-only, independent, no live-system access, no self-fan-out, and no final-decision authority.
- Model route is `minimax-m3` for these admitted bulk/read slices; use a fresh worker per slice.
- Coordinator synthesis starts only when every slice returns a matching `PASS` handoff with artifact digest, check evidence, and a verifier different from the worker.

**FACT:** this package does not dispatch MiniMax. It only emits a machine-readable plan with `dispatch_enabled: false`.

## Approval gates

### Stage 1A — live read-only laptop-Herdr status

**APPROVAL REQUIRED:** Shaan must explicitly approve read-only use of the existing Herdr discovery/status transport from this package.

Before approval can be exercised, implementation must add and pass:

- A transport interface separate from `FixtureHerdrAdapter`; the fixture adapter stays the default in tests.
- A hard allowlist of read-only Herdr operations and an automated proof that submit/type/key/process-control methods are unreachable.
- Snapshot-to-binding conversion that applies the same workspace/tab/registered-pane/role/task/CWD/freshness checks used by replay.
- Timeouts, bounded output, redaction, and receipts that record the discovery evidence digest without terminal contents.
- Replay/live parity tests for stale panes, duplicate labels, role mismatch, unavailable sessions, and changing terminal IDs.
- A runtime feature flag defaulting to off and a rollback test.

Approval unlocks only `STATUS_LOOKUP` and target discovery. It does not unlock composer inspection, typing, submission, agent dispatch, or task writes.

### Stage 1B — durable idempotency and task lookup

**APPROVAL REQUIRED:** approve a narrow adapter to the existing task-management/system-of-record lane and select its existing durable receipt location.

Required before enablement:

- Reuse the existing `TASK-*` record; no new task database or shadow status field.
- Store only request/action fingerprints, receipt ID, task ID, terminal verdict, and expiry using the existing durable mechanism.
- Define retry semantics for `NEEDS_CONFIRMATION`, `BLOCKED`, and transport-unknown outcomes.
- Add crash/restart, concurrent-duplicate, and conflicting-request tests.
- Prove that voice receipts link to task artifacts instead of copying task history.

### Stage 2A — existing-agent dispatch through laptop Herdr

**APPROVAL REQUIRED:** Shaan must explicitly approve live message submission after reviewing a shadow-run evidence bundle from Stage 1A.

Required before enablement:

- Use the existing Herdr messaging path; do not create a terminal transport.
- Limit v1 to already-running, positively bound agents. No pane creation, agent spawning, interrupt, or takeover.
- Require tier-2 explicit confirmation tied to the canonical action fingerprint and expire it after a short window or any payload change.
- Re-resolve target immediately before typing, type only into a verified empty real composer, then submit and verify prompt disappearance plus a content marker.
- On uncertain submission, emit `BLOCKED/UNKNOWN`; never retry automatically.
- Persist the pre-submit and post-submit evidence digests in the durable receipt.
- Run replay, shadow, canary, and rollback tests. The canary target and message must be explicitly approved.

### Stage 2B — bounded MiniMax dispatch

**APPROVAL REQUIRED:** approve a specific existing worker-dispatch lane and the maximum concurrent fan-out.

Required before enablement:

- Translate only an already-admitted plan into the existing dispatch contract.
- Enforce fresh worker, no self-fan-out, read-only inputs, dedicated output path, timeout/budget, and no live-system tools at the dispatcher boundary.
- Prevent workers from changing coordinator-owned manifests or peer outputs.
- Require independent verification for every slice and coordinator-owned aggregate/synthesis.
- Record worker IDs, model route, output digests, checks, verifier IDs, and final synthesis receipt under the existing `TASK-*` identity.
- Test partial failure, timeout, malicious handoff, conflicting writes, repeated dispatch request, and mixed-version workers.

### Stage 3 — task mutations and broader voice actions

**APPROVAL REQUIRED:** approve each new mutating intent class separately. Tier-3 actions remain disabled until a high-assurance confirmation design, compensating action, audit path, and canary plan have been reviewed.

## Wiring sequence after approval

1. Keep the typed contracts and policy as the stable boundary.
2. Add one read-only Herdr adapter behind an off-by-default flag; compare it with replay snapshots.
3. Add durable receipts through the existing task/receipt mechanism.
4. Run shadow mode: produce proposed bindings/actions without sending.
5. Review misroute, duplicate, latency, and unknown-outcome evidence.
6. Enable one approved existing-agent canary; retain fail-closed behavior.
7. Separately approve bounded MiniMax dispatch only after its dispatcher/evidence gates pass.

No stage authorizes changes to Oracle Streaming or the current voice runtime. Those remain separate integration decisions.
