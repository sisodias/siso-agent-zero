"""Risk-tier and confirmation policy for offline Agent Zero voice actions."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ConfirmationKind, IntentKind, RiskTier, VoiceIntent


RISK_RANK = {RiskTier.T0: 0, RiskTier.T1: 1, RiskTier.T2: 2, RiskTier.T3: 3}
CONFIRMATION_RANK = {
    ConfirmationKind.NOT_NEEDED: 0,
    ConfirmationKind.PENDING: 0,
    ConfirmationKind.DENIED: -1,
    ConfirmationKind.VOICE_CONFIRMED: 1,
    ConfirmationKind.EXPLICIT_CONFIRMED: 2,
    ConfirmationKind.HIGH_ASSURANCE_CONFIRMED: 3,
}


@dataclass(frozen=True)
class PolicyRule:
    minimum_risk: RiskTier
    required_confirmation: ConfirmationKind


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    code: str
    message: str
    required_confirmation: ConfirmationKind | None = None


class VoiceActionPolicy:
    """Fail-closed policy. This package can only plan or inspect fixtures."""

    def __init__(self) -> None:
        self.rules = {
            IntentKind.STATUS: PolicyRule(RiskTier.T0, ConfirmationKind.NOT_NEEDED),
            IntentKind.CHECK_RESULT: PolicyRule(RiskTier.T0, ConfirmationKind.NOT_NEEDED),
            IntentKind.RECORD: PolicyRule(RiskTier.T1, ConfirmationKind.VOICE_CONFIRMED),
            IntentKind.CANCEL_PENDING: PolicyRule(RiskTier.T1, ConfirmationKind.VOICE_CONFIRMED),
            IntentKind.PLAN_MINIMAX_FANOUT: PolicyRule(RiskTier.T1, ConfirmationKind.VOICE_CONFIRMED),
            IntentKind.DELEGATE_EXISTING: PolicyRule(RiskTier.T2, ConfirmationKind.EXPLICIT_CONFIRMED),
        }

    def evaluate(self, intent: VoiceIntent) -> PolicyDecision:
        if not intent.dry_run:
            return PolicyDecision(False, "live_stage_disabled", "Only dry-run actions are enabled.")
        if intent.confirmation == ConfirmationKind.DENIED:
            return PolicyDecision(False, "confirmation_denied", "The user denied this action.")
        rule = self.rules.get(intent.intent)
        if rule is None:
            return PolicyDecision(False, "unsupported_intent", "The requested action is not allowlisted.")
        if RISK_RANK[intent.risk_tier] < RISK_RANK[rule.minimum_risk]:
            return PolicyDecision(
                False,
                "risk_understated",
                f"{intent.intent.value} requires at least {rule.minimum_risk.value}.",
                rule.required_confirmation,
            )
        if intent.risk_tier == RiskTier.T3:
            return PolicyDecision(
                False,
                "t3_stage_disabled",
                "T3 actions remain disabled even when high-assurance confirmation is present.",
                ConfirmationKind.HIGH_ASSURANCE_CONFIRMED,
            )
        required_rank = max(
            RISK_RANK[intent.risk_tier],
            CONFIRMATION_RANK[rule.required_confirmation],
        )
        if CONFIRMATION_RANK[intent.confirmation] < required_rank:
            required = {
                0: ConfirmationKind.NOT_NEEDED,
                1: ConfirmationKind.VOICE_CONFIRMED,
                2: ConfirmationKind.EXPLICIT_CONFIRMED,
                3: ConfirmationKind.HIGH_ASSURANCE_CONFIRMED,
            }[required_rank]
            return PolicyDecision(
                False,
                "confirmation_required",
                f"{intent.risk_tier.value} requires {required.value}.",
                required,
            )
        return PolicyDecision(True, "allowed_dry_run", "Policy allows fixture-only planning.")
