"""PAGE-01 (margins) and PAGE-02 (paper size)."""

from __future__ import annotations

import pytest
from docx.shared import Cm

from conftest import rule_ids, run_doc, run_sample
from tools.make_samples import make_clean, make_landscape_rotated


@pytest.mark.parametrize("rule_id", ["PAGE-01", "PAGE-02"])
def test_clean_has_no_finding(rule_id, demo_profile):
    assert rule_id not in rule_ids(run_sample("clean", demo_profile))


@pytest.mark.parametrize("rule_id", ["PAGE-01", "PAGE-02"])
def test_bad_sample_gives_exactly_that_finding(rule_id, demo_profile):
    assert rule_ids(run_sample(rule_id, demo_profile)) == [rule_id]


def test_page01_names_side_and_values(demo_profile):
    (finding,) = run_sample("PAGE-01", demo_profile)["findings"]
    assert "left" in finding["message"]
    assert "Section 1" in finding["message"]
    assert "left 2.50 cm" in finding["found"]
    assert "left 3.00 cm" in finding["expected"]
    assert finding["location"]["section_index"] == 0


def test_page01_tolerance(demo_profile):
    within = make_clean()
    within.sections[0].left_margin = Cm(3.04)  # inside ±0.05 cm
    assert "PAGE-01" not in rule_ids(run_doc(within, demo_profile))

    outside = make_clean()
    outside.sections[0].left_margin = Cm(3.1)
    assert rule_ids(run_doc(outside, demo_profile)) == ["PAGE-01"]


def test_page01_second_section_is_named(demo_profile):
    doc = make_clean()
    extra = doc.add_section()
    extra.right_margin = Cm(4)
    doc.add_paragraph("Appendix text.")
    (finding,) = run_doc(doc, demo_profile)["findings"]
    assert finding["rule_id"] == "PAGE-01"
    assert finding["message"].startswith("Section 2:")
    assert finding["location"]["section_index"] == 1


def test_landscape_section_with_rotated_margins_is_ok(demo_profile):
    report = run_doc(make_landscape_rotated(), demo_profile)
    assert "PAGE-01" not in rule_ids(report)
    assert "PAGE-02" not in rule_ids(report)  # landscape A4 is still A4


def test_page02_reports_found_size(demo_profile):
    (finding,) = run_sample("PAGE-02", demo_profile)["findings"]
    assert finding["expected"] == "A4"
    assert "Letter" in finding["found"]
