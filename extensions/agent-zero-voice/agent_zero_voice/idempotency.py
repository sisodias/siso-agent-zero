"""Process-local replay protection for Stage 0/1 dry-runs.

No database is created. Later durable execution must bind these keys to the existing
task/voice event machinery after explicit approval.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ActionReceipt, VoiceIntent


class IdempotencyConflict(ValueError):
    """The same request id was reused for a different action fingerprint."""


@dataclass(frozen=True)
class StoredAction:
    request_id: str
    fingerprint: str
    receipt: ActionReceipt


class IdempotencyLedger:
    def __init__(self) -> None:
        self._by_request: dict[str, StoredAction] = {}
        self._by_fingerprint: dict[str, StoredAction] = {}

    def lookup(self, intent: VoiceIntent) -> StoredAction | None:
        fingerprint = intent.action_fingerprint()
        by_request = self._by_request.get(intent.request_id)
        if by_request is not None and by_request.fingerprint != fingerprint:
            raise IdempotencyConflict(
                f"request_id {intent.request_id} was already used for a different action"
            )
        return by_request or self._by_fingerprint.get(fingerprint)

    def remember(self, intent: VoiceIntent, receipt: ActionReceipt) -> StoredAction:
        fingerprint = intent.action_fingerprint()
        current = self.lookup(intent)
        if current is not None:
            return current
        stored = StoredAction(intent.request_id, fingerprint, receipt)
        self._by_request[intent.request_id] = stored
        self._by_fingerprint[fingerprint] = stored
        return stored

    def __len__(self) -> int:
        return len(self._by_fingerprint)
