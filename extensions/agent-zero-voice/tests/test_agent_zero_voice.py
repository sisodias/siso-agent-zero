from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from jsonschema import Draft202012Validator, ValidationError


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(PACKAGE_ROOT))

from agent_zero_voice import (  # noqa: E402
    ActionState,
    AgentZeroVoiceCoordinator,
    ContractError,
    FixtureHerdrAdapter,
    HandoffVerdict,
    IdempotencyLedger,
    LiveTransportDisabled,
    MiniMaxAdmissionPolicy,
    TargetHint,
    TaskHandoff,
    VoiceIntent,
)
from agent_zero_voice.contracts import ArtifactEvidence, CheckEvidence  # noqa: E402
from agent_zero_voice.herdr_fixture import StaleBinding  # noqa: E402
from agent_zero_voice.orchestration import IndependentVerificationError  # noqa: E402


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def coordinator() -> AgentZeroVoiceCoordinator:
    return AgentZeroVoiceCoordinator(
        herdr=FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json")
    )


def accepted_minimax_dict() -> dict:
    return deepcopy(load_json("minimax-plans.json")["accepted"])


class ReplayTargetTests(unittest.TestCase):
    def test_target_failure_replays_and_stale_pane_hint(self) -> None:
        cases = load_json("replay-cases.json")["target_cases"]
        for case in cases:
            with self.subTest(case=case["name"]):
                receipt = coordinator().process(VoiceIntent.from_dict(case["intent"]))
                self.assertEqual(receipt.state.value, case["expected_state"])
                self.assertEqual(receipt.details["code"], case["expected_code"])
                if "expected_pane_id" in case:
                    self.assertIsNotNone(receipt.target_binding)
                    self.assertEqual(receipt.target_binding.pane_id, case["expected_pane_id"])
                    self.assertEqual(
                        receipt.target_binding.stale_hint_detected,
                        case["expected_stale_hint"],
                    )

    def test_status_read_does_not_treat_composer_as_a_submission(self) -> None:
        raw = deepcopy(load_json("replay-cases.json")["target_cases"][3]["intent"])
        raw.update(
            request_id="req-status-unsent",
            turn_id="turn-status-unsent",
            transcript_hash="sha256:" + "a" * 64,
            intent="status",
            risk_tier="T0",
            confirmation="not_needed",
        )
        receipt = coordinator().process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.DRY_RUN_READY)
        self.assertEqual(receipt.details["code"], "fixture_status_resolved")

    def test_live_send_is_structurally_disabled(self) -> None:
        adapter = FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json")
        self.assertFalse(adapter.live_transport_enabled)
        with self.assertRaises(LiveTransportDisabled):
            adapter.send_live("anything")

    def test_coordinator_never_calls_send_live(self) -> None:
        adapter = FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json")
        adapter.send_live = Mock(side_effect=AssertionError("live send was invoked"))
        raw = load_json("replay-cases.json")["target_cases"][0]["intent"]
        receipt = AgentZeroVoiceCoordinator(herdr=adapter).process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.DRY_RUN_READY)
        adapter.send_live.assert_not_called()

    def test_expired_binding_must_be_resolved_again(self) -> None:
        adapter = FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json")
        observed = datetime(2026, 7, 24, tzinfo=timezone.utc)
        binding = adapter.resolve_target(
            TargetHint(
                workspace="SISO Agent Base",
                tab="research-lane",
                role="research-worker",
                task_marker="TASK-9001",
            ),
            now=observed,
            ttl_seconds=30,
        )
        with self.assertRaises(StaleBinding):
            adapter.inspect_submission(binding, now=observed + timedelta(seconds=31))


class IdempotencyTests(unittest.TestCase):
    def test_duplicate_request_is_suppressed(self) -> None:
        raw = load_json("replay-cases.json")["duplicate_request"]
        ledger = IdempotencyLedger()
        subject = AgentZeroVoiceCoordinator(
            herdr=FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json"),
            idempotency=ledger,
        )
        first = subject.process(VoiceIntent.from_dict(raw))
        second = subject.process(VoiceIntent.from_dict(raw))
        self.assertEqual(first.state, ActionState.DRY_RUN_READY)
        self.assertEqual(second.state, ActionState.DUPLICATE)
        self.assertEqual(second.duplicate_of, raw["request_id"])
        self.assertEqual(len(ledger), 1)

    def test_duplicate_transcript_action_across_request_ids_is_suppressed(self) -> None:
        first_raw, second_raw = load_json("replay-cases.json")["duplicate_semantic_action"]
        subject = coordinator()
        first = subject.process(VoiceIntent.from_dict(first_raw))
        second = subject.process(VoiceIntent.from_dict(second_raw))
        self.assertEqual(first.state, ActionState.DRY_RUN_READY)
        self.assertEqual(second.state, ActionState.DUPLICATE)
        self.assertEqual(second.duplicate_of, first_raw["request_id"])

    def test_reused_request_id_with_different_action_is_rejected(self) -> None:
        raw = deepcopy(load_json("replay-cases.json")["duplicate_request"])
        subject = coordinator()
        subject.process(VoiceIntent.from_dict(raw))
        raw["goal"] = "A materially different status request"
        receipt = subject.process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.REJECTED)
        self.assertEqual(receipt.details["code"], "idempotency_conflict")


class PolicyAndContractTests(unittest.TestCase):
    def test_tier_two_requires_explicit_confirmation(self) -> None:
        raw = deepcopy(load_json("replay-cases.json")["target_cases"][0]["intent"])
        raw["request_id"] = "req-needs-confirmation"
        raw["confirmation"] = "voice_confirmed"
        receipt = coordinator().process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.NEEDS_CONFIRMATION)
        self.assertEqual(receipt.requires_confirmation.value, "explicit_confirmed")

    def test_tier_three_remains_disabled(self) -> None:
        raw = deepcopy(load_json("replay-cases.json")["duplicate_request"])
        raw.update(
            request_id="req-t3",
            risk_tier="T3",
            confirmation="high_assurance_confirmed",
        )
        receipt = coordinator().process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.REJECTED)
        self.assertEqual(receipt.details["code"], "t3_stage_disabled")

    def test_risk_understatement_fails_closed(self) -> None:
        raw = deepcopy(load_json("replay-cases.json")["target_cases"][0]["intent"])
        raw.update(request_id="req-risk-low", risk_tier="T0", confirmation="not_needed")
        receipt = coordinator().process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.REJECTED)
        self.assertEqual(receipt.details["code"], "risk_understated")

    def test_missing_handoff_evidence_is_invalid(self) -> None:
        with self.assertRaises(ContractError):
            TaskHandoff.from_dict(load_json("missing-evidence-handoff.json"))

    def test_json_schema_required_keys_match_executable_wire_shapes(self) -> None:
        status_raw = load_json("replay-cases.json")["duplicate_request"]
        intent = VoiceIntent.from_dict(status_raw)
        receipt = coordinator().process(intent)
        binding = receipt.target_binding
        self.assertIsNotNone(binding)
        handoff = TaskHandoff(
            verdict=HandoffVerdict.PASS,
            task_id="TASK-9002",
            action_id="azv-schema",
            outcome="Fixture handoff",
            worker="minimax-worker",
            model_served="minimax-m3",
            independent_verified_by="independent-verifier",
            artifacts=(ArtifactEvidence("research/example.json", "sha256:" + "b" * 64),),
            checks=(CheckEvidence("fixture-check", 0, "exit 0"),),
            open_risks=(),
            completed_at="2026-07-24T00:00:00+00:00",
            slice_id="fixture",
        )
        pairs = (
            ("voice-intent.v1.schema.json", intent.to_dict()),
            ("target-binding.v1.schema.json", binding.to_dict()),
            ("action-receipt.v1.schema.json", receipt.to_dict()),
            ("task-handoff.v1.schema.json", handoff.to_dict()),
        )
        for schema_name, payload in pairs:
            with self.subTest(schema=schema_name):
                schema = json.loads((PACKAGE_ROOT / "contracts" / schema_name).read_text())
                Draft202012Validator.check_schema(schema)
                Draft202012Validator(schema).validate(payload)
                self.assertEqual(set(schema["required"]), set(payload))
                self.assertFalse(set(payload) - set(schema["properties"]))

    def test_missing_evidence_handoff_fails_json_schema(self) -> None:
        schema = json.loads(
            (PACKAGE_ROOT / "contracts" / "task-handoff.v1.schema.json").read_text()
        )
        with self.assertRaises(ValidationError):
            Draft202012Validator(schema).validate(load_json("missing-evidence-handoff.json"))

    def test_voice_intent_round_trip_is_stable(self) -> None:
        intent = VoiceIntent.from_dict(accepted_minimax_dict())
        self.assertEqual(VoiceIntent.from_dict(intent.to_dict()), intent)

    def test_external_contract_rejects_truthy_strings_and_bad_confidence(self) -> None:
        base = accepted_minimax_dict()
        mutations = (
            ("string dry_run", lambda raw: raw.update(dry_run="false")),
            ("string worker flag", lambda raw: raw["minimax_slices"][0].update(self_fan_out="false")),
            ("bad confidence", lambda raw: raw.update(confidence="certain")),
        )
        for name, mutate in mutations:
            with self.subTest(case=name):
                raw = deepcopy(base)
                mutate(raw)
                with self.assertRaises(ContractError):
                    VoiceIntent.from_dict(raw)


class MiniMaxOrchestrationTests(unittest.TestCase):
    def test_plan_only_admission_encodes_worker_limits_and_coordinator_ownership(self) -> None:
        receipt = coordinator().process(VoiceIntent.from_dict(accepted_minimax_dict()))
        self.assertEqual(receipt.state, ActionState.DRY_RUN_ADMITTED)
        plan = receipt.details["plan"]
        self.assertEqual(plan["model_route"], "minimax-m3")
        self.assertFalse(plan["dispatch_enabled"])
        self.assertTrue(plan["fresh_worker_per_slice"])
        self.assertFalse(plan["worker_may_self_fan_out"])
        self.assertFalse(plan["worker_may_touch_live_systems"])
        self.assertFalse(plan["worker_is_final_decision_maker"])
        self.assertEqual(plan["aggregation_owner"], "agent-zero-coordinator")
        self.assertEqual(plan["synthesis_owner"], "agent-zero-coordinator")
        self.assertTrue(plan["independent_verifier_required"])

    def test_admission_fixture_rejections_fail_closed(self) -> None:
        fixture = load_json("minimax-plans.json")
        for index, case in enumerate(fixture["rejections"]):
            with self.subTest(case=case["name"]):
                raw = deepcopy(fixture["accepted"])
                raw["request_id"] = f"req-rejected-{index}"
                raw["minimax_slices"][case["slice"]][case["field"]] = case["value"]
                receipt = coordinator().process(VoiceIntent.from_dict(raw))
                self.assertEqual(receipt.state, ActionState.DRY_RUN_BLOCKED)
                self.assertEqual(receipt.details["code"], case["expected_code"])

    def test_configured_fanout_cap_is_enforced(self) -> None:
        raw = accepted_minimax_dict()
        subject = AgentZeroVoiceCoordinator(
            herdr=FixtureHerdrAdapter.from_path(FIXTURES / "herdr-registry.json"),
            minimax=MiniMaxAdmissionPolicy(max_workers=2),
        )
        receipt = subject.process(VoiceIntent.from_dict(raw))
        self.assertEqual(receipt.state, ActionState.DRY_RUN_BLOCKED)
        self.assertEqual(receipt.details["code"], "fanout_cap_exceeded")

    def test_synthesis_requires_all_artifacts_and_independent_verifiers(self) -> None:
        intent = VoiceIntent.from_dict(accepted_minimax_dict())
        policy = MiniMaxAdmissionPolicy()
        plan = policy.admit(intent, "azv-synthesis")
        handoffs = []
        with TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            for index, item in enumerate(plan.slices):
                artifact_path = artifact_root / item.output_path
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                content = json.dumps({"slice": item.slice_id}).encode()
                artifact_path.write_bytes(content)
                handoffs.append(
                    TaskHandoff(
                        verdict=HandoffVerdict.PASS,
                        task_id=plan.root_task_id,
                        action_id=plan.action_id,
                        outcome=f"Completed {item.slice_id}",
                        worker=f"minimax-worker-{index}",
                        model_served="minimax-m3",
                        independent_verified_by=f"verifier-{index}",
                        artifacts=(
                            ArtifactEvidence(
                                item.output_path,
                                "sha256:" + sha256(content).hexdigest(),
                            ),
                        ),
                        checks=(CheckEvidence("fixture-check", 0, "digest verified"),),
                        open_risks=(),
                        completed_at="2026-07-24T00:00:00+00:00",
                        slice_id=item.slice_id,
                    )
                )
            manifest = policy.prepare_synthesis_manifest(
                plan,
                handoffs,
                artifact_root=artifact_root,
            )
            self.assertTrue(manifest.ready)
            self.assertEqual(manifest.coordinator_owner, "agent-zero-coordinator")
            self.assertEqual(set(manifest.output_paths), {item.output_path for item in plan.slices})

            missing_one = handoffs[:-1]
            with self.assertRaises(IndependentVerificationError):
                policy.prepare_synthesis_manifest(plan, missing_one, artifact_root=artifact_root)

    def test_worker_cannot_self_verify_a_pass(self) -> None:
        with self.assertRaises(ContractError):
            TaskHandoff(
                verdict=HandoffVerdict.PASS,
                task_id="TASK-9002",
                action_id="azv-self-verify",
                outcome="Improperly self-verified",
                worker="same-agent",
                model_served="minimax-m3",
                independent_verified_by="same-agent",
                artifacts=(ArtifactEvidence("research/x", "sha256:" + "c" * 64),),
                checks=(CheckEvidence("fixture-check", 0, "claimed pass"),),
                open_risks=(),
                completed_at="2026-07-24T00:00:00+00:00",
                slice_id="x",
            )


class StaticSafetyTests(unittest.TestCase):
    def test_package_has_no_live_transport_or_voice_runtime_imports(self) -> None:
        forbidden_roots = {"subprocess", "socket", "requests", "httpx", "websockets"}
        forbidden_prefixes = ("extensions.voice", "oracle")
        violations = []
        for source_path in (PACKAGE_ROOT / "agent_zero_voice").glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                for name in names:
                    external_herdr = name == "herdr" or name.startswith("herdr.")
                    if (
                        name.split(".")[0] in forbidden_roots
                        or name.startswith(forbidden_prefixes)
                        or external_herdr
                    ):
                        violations.append(f"{source_path.name}: {name}")
        self.assertEqual(violations, [])

    def test_readme_local_links_resolve(self) -> None:
        readme = (PACKAGE_ROOT / "README.md").read_text(encoding="utf-8")
        targets = re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        local_targets = [target for target in targets if "://" not in target]
        missing = [
            target
            for target in local_targets
            if not (PACKAGE_ROOT / target.split("#", 1)[0]).resolve().exists()
        ]
        self.assertGreaterEqual(len(local_targets), 6)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
