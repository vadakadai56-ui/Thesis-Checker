"""HEAD-03: no skipped heading levels."""

from __future__ import annotations

from conftest import rule_ids, run_doc, run_sample
from tools.make_samples import build_document, clean_blocks


def test_clean_has_no_finding(demo_profile):
    assert "HEAD-03" not in rule_ids(run_sample("clean", demo_profile))


def test_bad_sample_gives_exactly_that_finding(demo_profile):
    report = run_sample("HEAD-03", demo_profile)
    assert rule_ids(report) == ["HEAD-03"]
    (finding,) = report["findings"]
    assert finding["message"] == "Heading level jumps from 1 to 3 (level 2 is skipped)."
    assert finding["location"]["snippet"] == "1.1.1. Data set"  # its level-2 parent is gone


def test_first_heading_not_level_1(demo_profile):
    blocks = clean_blocks()
    blocks.insert(blocks.index(("hu", "Abstract")), ("h2", "Preface"))
    report = run_doc(build_document(blocks), demo_profile)
    head03 = [f for f in report["findings"] if f["rule_id"] == "HEAD-03"]
    assert len(head03) == 1
    assert "first heading is level 2" in head03[0]["message"]


def test_no_headings_is_skipped_not_an_error(demo_profile):
    blocks = [("p", "Just one paragraph, no headings at all.")]
    report = run_doc(build_document(blocks), demo_profile)
    assert "HEAD-03" not in rule_ids(report)
    skipped = {s["rule_id"]: s["reason"] for s in report["skipped_rules"]}
    assert "No headings found" in skipped["HEAD-03"]
