"""The readiness score formula (BUILD_PROMPT §4c)."""

from __future__ import annotations

import math

import pytest

from conftest import run_sample
from thesischeck.model import Finding, Location
from thesischeck.scoring import band_for, score


def _f(rule_id: str, severity: str, fixed: bool = False) -> Finding:
    return Finding(
        id="x", rule_id=rule_id, category="text", severity=severity, message="m",
        rule_text="r", guideline_ref="g", location=Location(), expected=None, found=None,
        fixable=False, fixed=fixed,
    )  # fmt: skip


def test_no_findings_is_100_ready():
    assert score([], set()) == {
        "version": 1, "value": 100, "band": "Ready", "penalty": 0, "capped": False,
    }  # fmt: skip


@pytest.mark.parametrize(
    ("severity", "expected"),
    [("error", round(100 * math.exp(-5 / 60))), ("warning", 97), ("info", 99)],
)
def test_weights(severity, expected):
    assert score([_f("TEXT-01", severity)], set())["value"] == expected


def test_at_most_five_findings_count_per_rule():
    many = [_f("TEXT-01", "error") for _ in range(50)]
    five = [_f("TEXT-01", "error") for _ in range(5)]
    assert score(many, set()) == score(five, set())
    assert score(five, set())["penalty"] == 25


def test_rules_add_up():
    findings = [_f("TEXT-01", "error"), _f("TEXT-02", "warning"), _f("CONS-01", "info")]
    result = score(findings, set())
    assert result["penalty"] == 7.5
    assert result["value"] == round(100 * math.exp(-7.5 / 60))


def test_blocking_rule_caps_at_69():
    result = score([_f("STRUCT-01", "error")], {"STRUCT-01"})
    assert result["value"] == 69
    assert result["capped"] is True
    assert result["band"] == "Needs work"


def test_cap_only_lowers():
    many = [_f(f"R{i}", "error") for i in range(10)]  # already far below 69
    result = score(many, {"R1"})
    assert result["value"] < 69 and result["capped"] is False


@pytest.mark.parametrize(
    ("value", "band"),
    [(100, "Ready"), (90, "Ready"), (89, "Nearly ready"), (70, "Nearly ready"),
     (69, "Needs work"), (0, "Needs work")],
)  # fmt: skip
def test_bands(value, band):
    assert band_for(value) == band


def test_fixed_findings_do_not_count():
    assert score([_f("TEXT-01", "error", fixed=True)], set())["value"] == 100


def test_reports_carry_the_score(demo_profile):
    assert run_sample("clean", demo_profile)["score"]["value"] == 100
    blocked = run_sample("STRUCT-01", demo_profile)["score"]
    assert blocked == {**blocked, "value": 69, "capped": True}
