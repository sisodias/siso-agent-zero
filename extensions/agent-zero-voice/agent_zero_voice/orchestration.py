"""Admission control for plan-only bounded MiniMax fan-out."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

from .contracts import HandoffVerdict, IntentKind, MiniMaxSlice, TaskHandoff, VoiceIntent


class AdmissionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class IndependentVerificationError(ValueError):
    pass


@dataclass(frozen=True)
class MiniMaxFanoutPlan:
    action_id: str
    root_task_id: str
    slices: tuple[MiniMaxSlice, ...]
    model_route: str
    max_parallel: int
    fresh_worker_per_slice: bool
    dispatch_enabled: bool
    worker_may_self_fan_out: bool
    worker_may_touch_live_systems: bool
    worker_is_final_decision_maker: bool
    aggregation_owner: str
    synthesis_owner: str
    independent_verifier_required: bool
    constraints: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "root_task_id": self.root_task_id,
            "slices": [item.to_dict() for item in self.slices],
            "model_route": self.model_route,
            "max_parallel": self.max_parallel,
            "fresh_worker_per_slice": self.fresh_worker_per_slice,
            "dispatch_enabled": self.dispatch_enabled,
            "worker_may_self_fan_out": self.worker_may_self_fan_out,
            "worker_may_touch_live_systems": self.worker_may_touch_live_systems,
            "worker_is_final_decision_maker": self.worker_is_final_decision_maker,
            "aggregation_owner": self.aggregation_owner,
            "synthesis_owner": self.synthesis_owner,
            "independent_verifier_required": self.independent_verifier_required,
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True)
class SynthesisManifest:
    ready: bool
    root_task_id: str
    action_id: str
    coordinator_owner: str
    output_paths: tuple[str, ...]
    worker_handoffs: tuple[str, ...]
    independent_verifiers: tuple[str, ...]


def _safe_relative_path(value: str, field_name: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise AdmissionError("unsafe_output_path", f"{field_name} must be a safe repo-relative path")
    return path


class MiniMaxAdmissionPolicy:
    """Admit only clear, independent, read-heavy slices; never dispatch them."""

    HARD_MAX_WORKERS = 5

    def __init__(self, max_workers: int = 4) -> None:
        if max_workers < 2 or max_workers > self.HARD_MAX_WORKERS:
            raise ValueError(f"max_workers must be between 2 and {self.HARD_MAX_WORKERS}")
        self.max_workers = max_workers

    def admit(self, intent: VoiceIntent, action_id: str) -> MiniMaxFanoutPlan:
        if intent.intent != IntentKind.PLAN_MINIMAX_FANOUT:
            raise AdmissionError("wrong_intent", "MiniMax admission requires plan_minimax_fanout")
        slices = intent.minimax_slices
        if len(slices) < 2:
            raise AdmissionError("fanout_not_justified", "Fan-out requires at least two independent slices")
        if len(slices) > self.max_workers:
            raise AdmissionError(
                "fanout_cap_exceeded",
                f"Requested {len(slices)} slices; configured cap is {self.max_workers}",
            )

        slice_ids: set[str] = set()
        output_paths: set[str] = set()
        all_output_paths = {item.output_path for item in slices}
        expected_root = PurePosixPath("research", "agent-zero-voice-runs", intent.task_id)
        for item in slices:
            if item.slice_id in slice_ids:
                raise AdmissionError("duplicate_slice_id", f"Duplicate slice id: {item.slice_id}")
            slice_ids.add(item.slice_id)
            if not item.independent:
                raise AdmissionError("dependent_slice", f"Slice {item.slice_id} is not independent")
            if not item.read_only:
                raise AdmissionError("write_scope_rejected", f"Slice {item.slice_id} is not read-only")
            if item.self_fan_out:
                raise AdmissionError("self_fanout_rejected", f"Slice {item.slice_id} may not self-fan-out")
            if item.touches_live_systems:
                raise AdmissionError("live_system_rejected", f"Slice {item.slice_id} may not touch live systems")
            if item.final_decision_maker:
                raise AdmissionError("worker_decision_rejected", f"Slice {item.slice_id} may not make the final decision")
            output = _safe_relative_path(item.output_path, "output_path")
            if output.parent != expected_root:
                raise AdmissionError(
                    "output_not_dedicated",
                    f"Slice {item.slice_id} output must be directly under {expected_root}",
                )
            if item.output_path in output_paths:
                raise AdmissionError("conflicting_output", f"Duplicate output path: {item.output_path}")
            output_paths.add(item.output_path)
            if any(source in all_output_paths for source in item.source_paths):
                raise AdmissionError(
                    "conflicting_write_read_path",
                    f"Slice {item.slice_id} reads another worker output path",
                )

        return MiniMaxFanoutPlan(
            action_id=action_id,
            root_task_id=intent.task_id,
            slices=slices,
            model_route="minimax-m3",
            max_parallel=min(self.max_workers, len(slices)),
            fresh_worker_per_slice=True,
            dispatch_enabled=False,
            worker_may_self_fan_out=False,
            worker_may_touch_live_systems=False,
            worker_is_final_decision_maker=False,
            aggregation_owner="agent-zero-coordinator",
            synthesis_owner="agent-zero-coordinator",
            independent_verifier_required=True,
            constraints=(
                "one bounded read-heavy slice per fresh MiniMax worker",
                "write only the dedicated output artifact",
                "no conflicting writes or cross-slice dependencies",
                "no self-fan-out, live-system mutation, or final decision",
                "coordinator aggregates; an independent verifier gates synthesis",
            ),
        )

    def prepare_synthesis_manifest(
        self,
        plan: MiniMaxFanoutPlan,
        handoffs: Iterable[TaskHandoff],
        *,
        artifact_root: Path,
        path_exists: Callable[[Path], bool] | None = None,
    ) -> SynthesisManifest:
        exists = path_exists or Path.exists
        by_slice: dict[str, TaskHandoff] = {}
        for handoff in handoffs:
            if not handoff.slice_id:
                raise IndependentVerificationError("Every MiniMax handoff requires slice_id")
            if handoff.slice_id in by_slice:
                raise IndependentVerificationError(f"Duplicate handoff for {handoff.slice_id}")
            by_slice[handoff.slice_id] = handoff

        expected_ids = {item.slice_id for item in plan.slices}
        if set(by_slice) != expected_ids:
            raise IndependentVerificationError("Handoff set does not match admitted slices")

        verifier_names: list[str] = []
        worker_names: list[str] = []
        output_paths: list[str] = []
        for item in plan.slices:
            handoff = by_slice[item.slice_id]
            if handoff.verdict != HandoffVerdict.PASS:
                raise IndependentVerificationError(f"Slice {item.slice_id} did not PASS")
            if handoff.task_id != plan.root_task_id or handoff.action_id != plan.action_id:
                raise IndependentVerificationError(f"Slice {item.slice_id} task/action identity mismatch")
            artifact = next((a for a in handoff.artifacts if a.path == item.output_path), None)
            if artifact is None:
                raise IndependentVerificationError(f"Slice {item.slice_id} missing its dedicated output")
            artifact_path = artifact_root / item.output_path
            if not exists(artifact_path):
                raise IndependentVerificationError(f"Artifact does not exist: {item.output_path}")
            actual_digest = "sha256:" + sha256(artifact_path.read_bytes()).hexdigest()
            if actual_digest != artifact.sha256:
                raise IndependentVerificationError(f"Artifact digest mismatch: {item.output_path}")
            if handoff.worker == handoff.independent_verified_by:
                raise IndependentVerificationError(f"Slice {item.slice_id} was self-verified")
            worker_names.append(handoff.worker)
            verifier_names.append(str(handoff.independent_verified_by))
            output_paths.append(item.output_path)

        return SynthesisManifest(
            ready=True,
            root_task_id=plan.root_task_id,
            action_id=plan.action_id,
            coordinator_owner=plan.synthesis_owner,
            output_paths=tuple(output_paths),
            worker_handoffs=tuple(worker_names),
            independent_verifiers=tuple(verifier_names),
        )
