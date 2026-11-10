"""Run the profile's enabled rules on a DocumentView and collect findings. READ ONLY."""

from __future__ import annotations

from .document_view import DocumentView
from .model import Finding, Profile, SkippedRule
from .rule_ids import ALL_RULE_IDS
from .rules import RuleContext, SkipRule, get_rule

REASON_PENDING = "Not checked yet: waiting for the faculty formatting guideline."
REASON_NOT_IMPLEMENTED = "Not checked yet: this rule is not implemented in this version."


def run_checks(view: DocumentView, profile: Profile) -> tuple[list[Finding], list[SkippedRule]]:
    findings: list[Finding] = []
    skipped: list[SkippedRule] = []

    # Go through rules in the fixed §5 order so reports are always in the same order.
    for rule_id in ALL_RULE_IDS:
        cfg = profile.rules.get(rule_id)
        if cfg is None:
            continue  # rule not in the profile = disabled on purpose
        if cfg.pending:
            skipped.append(SkippedRule(rule_id, REASON_PENDING))
            continue
        spec = get_rule(rule_id)
        if spec is None:
            skipped.append(SkippedRule(rule_id, REASON_NOT_IMPLEMENTED))
            continue

        ctx = RuleContext(view=view, cfg=cfg, spec=spec)
        try:
            spec.check(ctx)
        except SkipRule as skip:
            skipped.append(SkippedRule(rule_id, skip.reason))
            continue
        findings.extend(ctx.findings)

    # Give each finding a stable ID like "TEXT-01#2".
    counters: dict[str, int] = {}
    for f in findings:
        counters[f.rule_id] = counters.get(f.rule_id, 0) + 1
        f.id = f"{f.rule_id}#{counters[f.rule_id]}"
    return findings, skipped
