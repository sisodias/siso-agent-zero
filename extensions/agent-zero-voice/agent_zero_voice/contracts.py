"""Typed contracts shared by the offline Agent Zero voice coordinator.

The module deliberately contains no transport, credential, process, or database code.
It validates the same shapes published as JSON Schema under ../contracts/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence


TASK_ID_RE = re.compile(r"^TASK-[0-9]{4,}(?:\.[0-9]+)?$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when an external contract fails validation."""


class RiskTier(str, Enum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class ConfirmationKind(str, Enum):
    NOT_NEEDED = "not_needed"
    PENDING = "pending"
    VOICE_CONFIRMED = "voice_confirmed"
    EXPLICIT_CONFIRMED = "explicit_confirmed"
    HIGH_ASSURANCE_CONFIRMED = "high_assurance_confirmed"
    DENIED = "denied"


class IntentKind(str, Enum):
    STATUS = "status"
    RECORD = "record"
    DELEGATE_EXISTING = "delegate_existing"
    CHECK_RESULT = "check_result"
    CANCEL_PENDING = "cancel_pending"
    PLAN_MINIMAX_FANOUT = "plan_minimax_fanout"


class ActionState(str, Enum):
    NEEDS_CONFIRMATION = "needs_confirmation"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    DRY_RUN_READY = "dry_run_ready"
    DRY_RUN_BLOCKED = "dry_run_blocked"
    DRY_RUN_ADMITTED = "dry_run_admitted"


class HandoffVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} must be a non-empty string")
    return value.strip()


def _enum(enum_type: type[Enum], value: Any, field_name: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ContractError(f"{field_name} must be one of: {allowed}") from exc


def _string_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ContractError(f"{field_name} must be an array of strings")
    result = tuple(_required_text(value, field_name) for value in values)
    return result


def _strict_bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field_name} must be a boolean")
    return value


def _confidence(value: Any) -> float:
    if isinstance(value, bool):
        raise ContractError("confidence must be a number between 0 and 1")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError("confidence must be a number between 0 and 1") from exc
    if not 0.0 <= result <= 1.0:
        raise ContractError("confidence must be between 0 and 1")
    return result


@dataclass(frozen=True)
class TargetHint:
    workspace: str
    tab: str
    role: str
    task_marker: str | None = None
    cwd: str | None = None
    remembered_pane_id: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.workspace, "target_hint.workspace")
        _required_text(self.tab, "target_hint.tab")
        _required_text(self.role, "target_hint.role")
        if self.task_marker is not None and not TASK_ID_RE.match(self.task_marker):
            raise ContractError("target_hint.task_marker must be a TASK-* id")
        if self.cwd is not None:
            _required_text(self.cwd, "target_hint.cwd")
        if self.remembered_pane_id is not None:
            _required_text(self.remembered_pane_id, "target_hint.remembered_pane_id")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TargetHint":
        return cls(
            workspace=_required_text(data.get("workspace"), "target_hint.workspace"),
            tab=_required_text(data.get("tab"), "target_hint.tab"),
            role=_required_text(data.get("role"), "target_hint.role"),
            task_marker=data.get("task_marker"),
            cwd=data.get("cwd"),
            remembered_pane_id=data.get("remembered_pane_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "tab": self.tab,
            "role": self.role,
            **({"task_marker": self.task_marker} if self.task_marker else {}),
            **({"cwd": self.cwd} if self.cwd else {}),
            **({"remembered_pane_id": self.remembered_pane_id} if self.remembered_pane_id else {}),
        }


@dataclass(frozen=True)
class MiniMaxSlice:
    slice_id: str
    objective: str
    source_paths: tuple[str, ...]
    output_path: str
    independent: bool = True
    read_only: bool = True
    self_fan_out: bool = False
    touches_live_systems: bool = False
    final_decision_maker: bool = False

    def __post_init__(self) -> None:
        _required_text(self.slice_id, "minimax_slices.slice_id")
        _required_text(self.objective, "minimax_slices.objective")
        if not self.source_paths:
            raise ContractError("minimax_slices.source_paths must not be empty")
        for path in self.source_paths:
            _required_text(path, "minimax_slices.source_paths")
        _required_text(self.output_path, "minimax_slices.output_path")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MiniMaxSlice":
        return cls(
            slice_id=_required_text(data.get("slice_id"), "minimax_slices.slice_id"),
            objective=_required_text(data.get("objective"), "minimax_slices.objective"),
            source_paths=_string_tuple(data.get("source_paths"), "minimax_slices.source_paths"),
            output_path=_required_text(data.get("output_path"), "minimax_slices.output_path"),
            independent=_strict_bool(data.get("independent", True), "minimax_slices.independent"),
            read_only=_strict_bool(data.get("read_only", True), "minimax_slices.read_only"),
            self_fan_out=_strict_bool(data.get("self_fan_out", False), "minimax_slices.self_fan_out"),
            touches_live_systems=_strict_bool(
                data.get("touches_live_systems", False),
                "minimax_slices.touches_live_systems",
            ),
            final_decision_maker=_strict_bool(
                data.get("final_decision_maker", False),
                "minimax_slices.final_decision_maker",
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "slice_id": self.slice_id,
            "objective": self.objective,
            "source_paths": list(self.source_paths),
            "output_path": self.output_path,
            "independent": self.independent,
            "read_only": self.read_only,
            "self_fan_out": self.self_fan_out,
            "touches_live_systems": self.touches_live_systems,
            "final_decision_maker": self.final_decision_maker,
        }


@dataclass(frozen=True)
class VoiceIntent:
    request_id: str
    turn_id: str
    transcript_hash: str
    intent: IntentKind
    goal: str
    task_id: str
    risk_tier: RiskTier
    confirmation: ConfirmationKind
    confidence: float
    constraints: tuple[str, ...] = ()
    target_hint: TargetHint | None = None
    minimax_slices: tuple[MiniMaxSlice, ...] = ()
    dry_run: bool = True

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _required_text(self.turn_id, "turn_id")
        if not SHA256_RE.match(self.transcript_hash):
            raise ContractError("transcript_hash must be sha256:<64 lowercase hex chars>")
        _required_text(self.goal, "goal")
        if not TASK_ID_RE.match(self.task_id):
            raise ContractError("task_id must be a TASK-* id from the existing task system")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ContractError("confidence must be between 0 and 1")
        if not self.dry_run:
            raise ContractError("Stage 0/1 package accepts dry_run=true only")
        if self.intent == IntentKind.PLAN_MINIMAX_FANOUT and not self.minimax_slices:
            raise ContractError("plan_minimax_fanout requires minimax_slices")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VoiceIntent":
        target_data = data.get("target_hint")
        if target_data is not None and not isinstance(target_data, Mapping):
            raise ContractError("target_hint must be an object or null")
        slices_data = data.get("minimax_slices", [])
        if not isinstance(slices_data, list):
            raise ContractError("minimax_slices must be an array")
        if any(not isinstance(item, Mapping) for item in slices_data):
            raise ContractError("every minimax_slices item must be an object")
        return cls(
            request_id=_required_text(data.get("request_id"), "request_id"),
            turn_id=_required_text(data.get("turn_id"), "turn_id"),
            transcript_hash=_required_text(data.get("transcript_hash"), "transcript_hash"),
            intent=_enum(IntentKind, data.get("intent"), "intent"),
            goal=_required_text(data.get("goal"), "goal"),
            task_id=_required_text(data.get("task_id"), "task_id"),
            risk_tier=_enum(RiskTier, data.get("risk_tier"), "risk_tier"),
            confirmation=_enum(ConfirmationKind, data.get("confirmation"), "confirmation"),
            confidence=_confidence(data.get("confidence")),
            constraints=_string_tuple(data.get("constraints", []), "constraints"),
            target_hint=TargetHint.from_dict(target_data) if isinstance(target_data, Mapping) else None,
            minimax_slices=tuple(MiniMaxSlice.from_dict(item) for item in slices_data),
            dry_run=_strict_bool(data.get("dry_run", True), "dry_run"),
        )

    def action_fingerprint(self) -> str:
        payload = {
            "transcript_hash": self.transcript_hash,
            "intent": self.intent.value,
            "goal": self.goal,
            "task_id": self.task_id,
            "risk_tier": self.risk_tier.value,
            "target_hint": self.target_hint.to_dict() if self.target_hint else None,
            "minimax_slices": [item.to_dict() for item in self.minimax_slices],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "transcript_hash": self.transcript_hash,
            "intent": self.intent.value,
            "goal": self.goal,
            "task_id": self.task_id,
            "risk_tier": self.risk_tier.value,
            "confirmation": self.confirmation.value,
            "confidence": self.confidence,
            "constraints": list(self.constraints),
            "target_hint": self.target_hint.to_dict() if self.target_hint else None,
            "minimax_slices": [item.to_dict() for item in self.minimax_slices],
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class TargetBinding:
    machine: str
    workspace_label: str
    tab_label: str
    terminal_id: str
    pane_id: str
    cwd: str
    role: str
    task_marker: str | None
    role_evidence_sha256: str
    agent_status: str
    registry_version: str
    resolved_at: str
    expires_at: str
    stale_hint_detected: bool = False

    def __post_init__(self) -> None:
        if self.machine != "laptop":
            raise ContractError("TargetBinding.machine must be laptop in Stage 1")
        for field_name in (
            "workspace_label", "tab_label", "terminal_id", "pane_id", "cwd",
            "role", "agent_status", "registry_version", "resolved_at", "expires_at",
        ):
            _required_text(getattr(self, field_name), field_name)
        if self.task_marker is not None and not TASK_ID_RE.match(self.task_marker):
            raise ContractError("task_marker must be a TASK-* id")
        if not SHA256_RE.match(self.role_evidence_sha256):
            raise ContractError("role_evidence_sha256 must be a sha256 digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "workspace_label": self.workspace_label,
            "tab_label": self.tab_label,
            "terminal_id": self.terminal_id,
            "pane_id": self.pane_id,
            "cwd": self.cwd,
            "role": self.role,
            "task_marker": self.task_marker,
            "role_evidence_sha256": self.role_evidence_sha256,
            "agent_status": self.agent_status,
            "registry_version": self.registry_version,
            "resolved_at": self.resolved_at,
            "expires_at": self.expires_at,
            "stale_hint_detected": self.stale_hint_detected,
        }


@dataclass(frozen=True)
class ArtifactEvidence:
    path: str
    sha256: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArtifactEvidence":
        return cls(
            path=_required_text(data.get("path"), "artifacts.path"),
            sha256=_required_text(data.get("sha256"), "artifacts.sha256"),
        )

    def __post_init__(self) -> None:
        _required_text(self.path, "artifacts.path")
        if not SHA256_RE.match(self.sha256):
            raise ContractError("artifacts.sha256 must be a sha256 digest")

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class CheckEvidence:
    command: str
    exit_code: int
    evidence: str

    def __post_init__(self) -> None:
        _required_text(self.command, "checks.command")
        if not isinstance(self.exit_code, int) or isinstance(self.exit_code, bool):
            raise ContractError("checks.exit_code must be an integer")
        _required_text(self.evidence, "checks.evidence")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CheckEvidence":
        return cls(
            command=_required_text(data.get("command"), "checks.command"),
            exit_code=data.get("exit_code"),
            evidence=_required_text(data.get("evidence"), "checks.evidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"command": self.command, "exit_code": self.exit_code, "evidence": self.evidence}


@dataclass(frozen=True)
class TaskHandoff:
    verdict: HandoffVerdict
    task_id: str
    action_id: str
    outcome: str
    worker: str
    model_served: str
    independent_verified_by: str | None
    artifacts: tuple[ArtifactEvidence, ...]
    checks: tuple[CheckEvidence, ...]
    open_risks: tuple[str, ...]
    completed_at: str
    slice_id: str | None = None

    def __post_init__(self) -> None:
        if not TASK_ID_RE.match(self.task_id):
            raise ContractError("handoff.task_id must be a TASK-* id")
        for field_name in ("action_id", "outcome", "worker", "model_served", "completed_at"):
            _required_text(getattr(self, field_name), f"handoff.{field_name}")
        if self.independent_verified_by is not None:
            _required_text(self.independent_verified_by, "handoff.independent_verified_by")
        if self.slice_id is not None:
            _required_text(self.slice_id, "handoff.slice_id")
        for risk in self.open_risks:
            _required_text(risk, "handoff.open_risks")
        if self.verdict == HandoffVerdict.PASS:
            if not self.artifacts:
                raise ContractError("PASS handoff requires at least one artifact with digest")
            if not self.checks:
                raise ContractError("PASS handoff requires verification checks")
            for check in self.checks:
                if check.exit_code != 0 or not check.evidence.strip():
                    raise ContractError("PASS handoff requires exit_code=0 and evidence for every check")
            verifier = _required_text(self.independent_verified_by, "handoff.independent_verified_by")
            if verifier == self.worker:
                raise ContractError("independent verifier must differ from worker")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskHandoff":
        artifacts = data.get("artifacts", [])
        checks = data.get("checks", [])
        if not isinstance(artifacts, list) or not isinstance(checks, list):
            raise ContractError("handoff artifacts and checks must be arrays")
        return cls(
            verdict=_enum(HandoffVerdict, data.get("verdict"), "handoff.verdict"),
            task_id=_required_text(data.get("task_id"), "handoff.task_id"),
            action_id=_required_text(data.get("action_id"), "handoff.action_id"),
            outcome=_required_text(data.get("outcome"), "handoff.outcome"),
            worker=_required_text(data.get("worker"), "handoff.worker"),
            model_served=_required_text(data.get("model_served"), "handoff.model_served"),
            independent_verified_by=data.get("independent_verified_by"),
            artifacts=tuple(ArtifactEvidence.from_dict(item) for item in artifacts),
            checks=tuple(CheckEvidence.from_dict(item) for item in checks),
            open_risks=_string_tuple(data.get("open_risks", []), "handoff.open_risks"),
            completed_at=_required_text(data.get("completed_at"), "handoff.completed_at"),
            slice_id=data.get("slice_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "task_id": self.task_id,
            "action_id": self.action_id,
            "outcome": self.outcome,
            "worker": self.worker,
            "model_served": self.model_served,
            "independent_verified_by": self.independent_verified_by,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "checks": [item.to_dict() for item in self.checks],
            "open_risks": list(self.open_risks),
            "completed_at": self.completed_at,
            "slice_id": self.slice_id,
        }


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    action_id: str
    task_id: str
    state: ActionState
    risk_tier: RiskTier
    dry_run: bool
    message: str
    proof: tuple[str, ...] = ()
    requires_confirmation: ConfirmationKind | None = None
    target_binding: TargetBinding | None = None
    duplicate_of: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required_text(self.request_id, "receipt.request_id")
        _required_text(self.action_id, "receipt.action_id")
        if not TASK_ID_RE.match(self.task_id):
            raise ContractError("receipt.task_id must be a TASK-* id")
        _required_text(self.message, "receipt.message")
        if not self.dry_run:
            raise ContractError("Stage 0/1 receipts must remain dry_run=true")

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_id": self.action_id,
            "task_id": self.task_id,
            "state": self.state.value,
            "risk_tier": self.risk_tier.value,
            "dry_run": self.dry_run,
            "message": self.message,
            "proof": list(self.proof),
            "requires_confirmation": self.requires_confirmation.value if self.requires_confirmation else None,
            "target_binding": self.target_binding.to_dict() if self.target_binding else None,
            "duplicate_of": self.duplicate_of,
            "details": dict(self.details),
        }
