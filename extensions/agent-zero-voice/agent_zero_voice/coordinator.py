"""Offline coordinator state machine for Stage 0 and Stage 1 dry-run."""

from __future__ import annotations

from dataclasses import replace

from .contracts import (
    ActionReceipt,
    ActionState,
    ConfirmationKind,
    IntentKind,
    VoiceIntent,
)
from .herdr_fixture import FixtureHerdrAdapter, TargetResolutionError
from .idempotency import IdempotencyConflict, IdempotencyLedger
from .orchestration import AdmissionError, MiniMaxAdmissionPolicy
from .policy import VoiceActionPolicy


def _action_id(intent: VoiceIntent) -> str:
    return f"azv_{intent.action_fingerprint()[:20]}"


class AgentZeroVoiceCoordinator:
    """Produce truthful dry-run receipts without performing external effects."""

    def __init__(
        self,
        *,
        herdr: FixtureHerdrAdapter,
        policy: VoiceActionPolicy | None = None,
        idempotency: IdempotencyLedger | None = None,
        minimax: MiniMaxAdmissionPolicy | None = None,
    ) -> None:
        self.herdr = herdr
        self.policy = policy if policy is not None else VoiceActionPolicy()
        self.idempotency = idempotency if idempotency is not None else IdempotencyLedger()
        self.minimax = minimax if minimax is not None else MiniMaxAdmissionPolicy()

    def process(self, intent: VoiceIntent) -> ActionReceipt:
        action_id = _action_id(intent)
        try:
            duplicate = self.idempotency.lookup(intent)
        except IdempotencyConflict as exc:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.REJECTED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=str(exc),
                proof=("idempotency conflict blocked before adapter evaluation",),
                details={"code": "idempotency_conflict"},
            )
        if duplicate is not None:
            return replace(
                duplicate.receipt,
                request_id=intent.request_id,
                state=ActionState.DUPLICATE,
                message="Duplicate transcript/action suppressed; no second action was planned.",
                proof=duplicate.receipt.proof + ("idempotency ledger matched existing fingerprint",),
                duplicate_of=duplicate.request_id,
            )

        policy = self.policy.evaluate(intent)
        if not policy.allowed:
            state = (
                ActionState.NEEDS_CONFIRMATION
                if policy.code == "confirmation_required"
                else ActionState.REJECTED
            )
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=state,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=policy.message,
                proof=("policy evaluated before all adapters",),
                requires_confirmation=policy.required_confirmation,
                details={"code": policy.code},
            )

        if intent.intent in (IntentKind.STATUS, IntentKind.DELEGATE_EXISTING):
            receipt = self._process_target_intent(intent, action_id)
        elif intent.intent == IntentKind.PLAN_MINIMAX_FANOUT:
            receipt = self._process_minimax_plan(intent, action_id)
        elif intent.intent == IntentKind.RECORD:
            receipt = ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_READY,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message="Would append through the existing task CLI; no task file was changed.",
                proof=("canonical task id validated", "task write adapter is not enabled"),
            )
        elif intent.intent == IntentKind.CHECK_RESULT:
            receipt = ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_READY,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message="Would validate a TaskHandoff; no live result source was queried.",
                proof=("TaskHandoff validator is available", "live result lookup is disabled"),
            )
        else:
            receipt = ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_READY,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message="Would cancel a pending action; no external state exists in fixture mode.",
                proof=("fixture-only coordinator has no live pending queue",),
            )

        self.idempotency.remember(intent, receipt)
        return receipt

    def _process_target_intent(self, intent: VoiceIntent, action_id: str) -> ActionReceipt:
        if intent.target_hint is None:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_BLOCKED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message="Target hint is required for fixture Herdr resolution.",
                proof=("no target adapter call performed",),
                details={"code": "target_hint_required"},
            )
        try:
            binding = self.herdr.resolve_target(intent.target_hint)
        except TargetResolutionError as exc:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_BLOCKED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=str(exc),
                proof=("fixture registry evaluated; no live Herdr command executed",),
                details={"code": exc.code},
            )
        if intent.intent == IntentKind.STATUS:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_READY,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message="Target and replayed status resolved; no live status source was queried.",
                proof=(
                    "workspace/tab matched uniquely",
                    "role and task marker matched bounded content evidence",
                    "fixture agent status was read without inspecting or changing the composer",
                    "live Herdr transport is disabled",
                ),
                target_binding=binding,
                details={"code": "fixture_status_resolved", "agent_status": binding.agent_status},
            )
        try:
            inspection = self.herdr.inspect_submission(binding)
        except TargetResolutionError as exc:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_BLOCKED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=str(exc),
                proof=("fixture binding revalidated; no live Herdr command executed",),
                target_binding=binding,
                details={"code": exc.code},
            )
        if not inspection.ready:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_BLOCKED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=inspection.message,
                proof=("target identity verified", "composer/status replay blocked submission"),
                target_binding=binding,
                details={"code": inspection.code},
            )
        return ActionReceipt(
            request_id=intent.request_id,
            action_id=action_id,
            task_id=intent.task_id,
            state=ActionState.DRY_RUN_READY,
            risk_tier=intent.risk_tier,
            dry_run=True,
            message="Target resolved and packet submission would be eligible; no message was sent.",
            proof=(
                "workspace/tab matched uniquely",
                "role and task marker matched bounded content evidence",
                "composer replay is clear",
                "live Herdr transport is disabled",
            ),
            target_binding=binding,
            details={"code": inspection.code},
        )

    def _process_minimax_plan(self, intent: VoiceIntent, action_id: str) -> ActionReceipt:
        try:
            plan = self.minimax.admit(intent, action_id)
        except AdmissionError as exc:
            return ActionReceipt(
                request_id=intent.request_id,
                action_id=action_id,
                task_id=intent.task_id,
                state=ActionState.DRY_RUN_BLOCKED,
                risk_tier=intent.risk_tier,
                dry_run=True,
                message=str(exc),
                proof=("MiniMax admission failed before any dispatch mechanism",),
                details={"code": exc.code},
            )
        return ActionReceipt(
            request_id=intent.request_id,
            action_id=action_id,
            task_id=intent.task_id,
            state=ActionState.DRY_RUN_ADMITTED,
            risk_tier=intent.risk_tier,
            dry_run=True,
            message=(
                f"Admitted {len(plan.slices)} bounded MiniMax slices for planning; dispatch is disabled."
            ),
            proof=(
                "all slices are independent and read-only",
                "dedicated output paths are unique",
                "fan-out is within admission cap",
                "self-fan-out/live mutation/final-decision flags are false",
                "coordinator synthesis and independent verification are required",
            ),
            details={"code": "minimax_plan_admitted", "plan": plan.to_dict()},
        )
