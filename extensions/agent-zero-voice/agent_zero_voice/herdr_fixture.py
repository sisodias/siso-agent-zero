"""Fixture/replay-only Herdr target resolution.

There is intentionally no live Herdr implementation in this package. The adapter
never imports subprocess, sockets, or credential machinery and cannot send messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import TargetBinding, TargetHint


class LiveTransportDisabled(RuntimeError):
    """Raised for every attempted live Herdr operation in Stage 0/1."""


class TargetResolutionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NoTarget(TargetResolutionError):
    def __init__(self, message: str) -> None:
        super().__init__("no_target", message)


class AmbiguousTarget(TargetResolutionError):
    def __init__(self, message: str) -> None:
        super().__init__("ambiguous_target", message)


class RoleMismatch(TargetResolutionError):
    def __init__(self, message: str) -> None:
        super().__init__("role_mismatch", message)


class StaleBinding(TargetResolutionError):
    def __init__(self, message: str) -> None:
        super().__init__("stale_binding", message)


@dataclass(frozen=True)
class SubmissionInspection:
    ready: bool
    code: str
    message: str


def _matching(items: list[Mapping[str, Any]], field: str, value: str) -> list[Mapping[str, Any]]:
    wanted = value.casefold().strip()
    return [item for item in items if str(item.get(field, "")).casefold().strip() == wanted]


class FixtureHerdrAdapter:
    """Resolve and verify a target exclusively from an in-memory replay snapshot."""

    live_transport_enabled = False

    def __init__(self, registry: Mapping[str, Any]) -> None:
        self.registry = dict(registry)
        for name in ("workspaces", "tabs", "panes"):
            if not isinstance(self.registry.get(name), list):
                raise ValueError(f"fixture registry requires a {name} array")

    @classmethod
    def from_path(cls, path: str | Path) -> "FixtureHerdrAdapter":
        with Path(path).open(encoding="utf-8") as handle:
            return cls(json.load(handle))

    def resolve_target(
        self,
        hint: TargetHint,
        *,
        now: datetime | None = None,
        ttl_seconds: int = 30,
    ) -> TargetBinding:
        workspaces = _matching(self.registry["workspaces"], "label", hint.workspace)
        if not workspaces:
            raise NoTarget(f"workspace not found: {hint.workspace}")
        if len(workspaces) != 1:
            raise AmbiguousTarget(f"workspace label is not unique: {hint.workspace}")
        workspace = workspaces[0]

        tabs = [
            tab for tab in _matching(self.registry["tabs"], "label", hint.tab)
            if tab.get("workspace_id") == workspace.get("workspace_id")
        ]
        if not tabs:
            raise NoTarget(f"tab not found in workspace {hint.workspace}: {hint.tab}")
        if len(tabs) != 1:
            raise AmbiguousTarget(f"tab label is not unique in {hint.workspace}: {hint.tab}")
        tab = tabs[0]

        panes = [pane for pane in self.registry["panes"] if pane.get("tab_id") == tab.get("tab_id")]
        panes = [pane for pane in panes if pane.get("terminal_id") and pane.get("agent_name")]
        if not panes:
            raise NoTarget(f"no registered agent in {hint.workspace}/{hint.tab}")
        if len(panes) != 1:
            raise AmbiguousTarget(f"multiple registered agents in {hint.workspace}/{hint.tab}")
        pane = panes[0]

        declared = pane.get("identity", {})
        declared_role = str(declared.get("role", ""))
        recent_content = str(pane.get("recent_content", ""))
        role_marker = f"role: {hint.role}".casefold()
        if declared_role.casefold() != hint.role.casefold() or role_marker not in recent_content.casefold():
            raise RoleMismatch(
                f"expected role {hint.role}; fixture declared {declared_role or '(missing)'}"
            )
        declared_task = declared.get("task_marker")
        if hint.task_marker:
            task_in_content = hint.task_marker.casefold() in recent_content.casefold()
            if declared_task != hint.task_marker or not task_in_content:
                raise RoleMismatch(
                    f"expected task marker {hint.task_marker}; fixture declared {declared_task}"
                )
        foreground_cwd = str(pane.get("foreground_cwd") or pane.get("cwd") or "")
        if hint.cwd and foreground_cwd != hint.cwd:
            raise RoleMismatch(f"expected cwd {hint.cwd}; fixture reported {foreground_cwd}")

        moment = now or datetime.now(timezone.utc)
        expires = moment + timedelta(seconds=ttl_seconds)
        digest = "sha256:" + sha256(recent_content.encode("utf-8")).hexdigest()
        pane_id = str(pane.get("pane_id"))
        return TargetBinding(
            machine="laptop",
            workspace_label=str(workspace.get("label")),
            tab_label=str(tab.get("label")),
            terminal_id=str(pane.get("terminal_id")),
            pane_id=pane_id,
            cwd=foreground_cwd,
            role=declared_role,
            task_marker=declared_task,
            role_evidence_sha256=digest,
            agent_status=str(pane.get("agent_status", "unknown")),
            registry_version=str(self.registry.get("registry_version", "fixture-unknown")),
            resolved_at=moment.isoformat(),
            expires_at=expires.isoformat(),
            stale_hint_detected=bool(
                hint.remembered_pane_id and hint.remembered_pane_id != pane_id
            ),
        )

    def inspect_submission(
        self,
        binding: TargetBinding,
        *,
        now: datetime | None = None,
    ) -> SubmissionInspection:
        """Re-resolve the terminal and evaluate replayed composer/status state."""
        moment = now or datetime.now(timezone.utc)
        if moment >= datetime.fromisoformat(binding.expires_at):
            raise StaleBinding("target binding expired; resolve target again")
        panes = [
            pane for pane in self.registry["panes"]
            if pane.get("terminal_id") == binding.terminal_id
        ]
        if len(panes) != 1:
            raise StaleBinding("terminal identity no longer resolves uniquely")
        pane = panes[0]
        if pane.get("pane_id") != binding.pane_id:
            raise StaleBinding("binding pane locator changed; resolve target again")
        declared = pane.get("identity", {})
        if not isinstance(declared, Mapping):
            raise StaleBinding("target identity metadata is no longer available")
        if str(declared.get("role", "")) != binding.role:
            raise StaleBinding("target role changed after resolution")
        if declared.get("task_marker") != binding.task_marker:
            raise StaleBinding("target task marker changed after resolution")
        foreground_cwd = str(pane.get("foreground_cwd") or pane.get("cwd") or "")
        if foreground_cwd != binding.cwd:
            raise StaleBinding("target foreground cwd changed after resolution")
        content_digest = "sha256:" + sha256(
            str(pane.get("recent_content", "")).encode("utf-8")
        ).hexdigest()
        if content_digest != binding.role_evidence_sha256:
            raise StaleBinding("role evidence changed after resolution")

        composer = pane.get("composer", {})
        if isinstance(composer, Mapping):
            composer_text = str(composer.get("text", ""))
            composer_is_real = bool(composer.get("is_real", False))
            if composer_text.strip() and composer_is_real:
                return SubmissionInspection(
                    False,
                    "unsent_composer",
                    "A real composer draft is already present; later live code must send Enter only and never retype.",
                )
        if str(pane.get("agent_status", "unknown")) == "working":
            return SubmissionInspection(
                False,
                "agent_busy",
                "The target is working; the dry-run will not plan an interrupting send.",
            )
        return SubmissionInspection(
            True,
            "would_submit",
            "Target is verified and composer is clear; live submission remains disabled.",
        )

    def send_live(self, *_args: Any, **_kwargs: Any) -> None:
        raise LiveTransportDisabled(
            "Stage 0/1 adapter is fixture-only; live Herdr send requires later explicit approval."
        )
