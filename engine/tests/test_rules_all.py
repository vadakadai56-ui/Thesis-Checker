"""One test per rule (BUILD_PROMPT §15): the clean sample gives no finding for the rule,
and the rule's own sample gives findings for exactly that rule and nothing else.
"""

from __future__ import annotations

import pytest

from conftest import SAMPLES_DIR, rule_ids, run_sample
from thesischeck.rule_ids import ALL_RULE_IDS
from thesischeck.rules import registered_rule_ids


def test_every_rule_is_implemented():
    assert registered_rule_ids() == sorted(ALL_RULE_IDS)


def test_every_rule_has_a_sample():
    missing = [r for r in ALL_RULE_IDS if not (SAMPLES_DIR / f"{r}.docx").exists()]
    assert missing == []


def test_clean_sample_has_no_findings_and_skips_nothing(demo_profile):
    report = run_sample("clean", demo_profile)
    assert report["findings"] == []
    assert report["skipped_rules"] == []  # every rule really ran
    assert report["score"]["value"] == 100


@pytest.mark.parametrize("rule_id", ALL_RULE_IDS)
def test_rule_sample_breaks_only_that_rule(rule_id, demo_profile):
    report = run_sample(rule_id, demo_profile)
    found = set(rule_ids(report))
    assert found == {rule_id}, report["findings"]
    for finding in report["findings"]:
        assert finding["guideline_ref"], "every finding cites the guideline"
        assert finding["how_to_fix"], "every finding says how to fix it"
        assert finding["message"].strip()
