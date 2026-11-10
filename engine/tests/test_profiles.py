"""Profile schema, compiler, and the "new university = one YAML file" promise (§7)."""

from __future__ import annotations

import copy
import json

import pytest
import yaml
from pydantic import ValidationError

from conftest import rule_ids, run_sample
from schema.profile_schema import ProfileModel
from thesischeck.checker import REASON_NOT_IMPLEMENTED, REASON_PENDING
from thesischeck.profile_loader import load_profile
from thesischeck.rule_ids import ALL_RULE_IDS
from tools.compile_profiles import PROFILES_DIR, compile_all, compile_profile_data


def _raw(name: str) -> dict:
    return yaml.safe_load((PROFILES_DIR / name).read_text(encoding="utf-8"))


def test_all_profiles_compile(tmp_path):
    profiles = compile_all(out=tmp_path)
    assert {p["id"] for p in profiles} >= {"demo", "rtu-fcsite-bachelor"}
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index["version"] == 1
    assert index["profiles"][-1]["id"] == "demo"  # the demo is listed last
    for p in profiles:
        load_profile(p)  # the stdlib loader (browser side) accepts the compiled JSON


def test_demo_is_clearly_labelled(demo_profile):
    assert demo_profile["demo"] is True
    assert "DEMO" in demo_profile["name"]
    assert all(r["rule_text"].startswith("DEMO") for r in demo_profile["rules"].values())


def test_rtu_profile_lists_every_rule(rtu_profile):
    assert set(rtu_profile["rules"]) == set(ALL_RULE_IDS)
    assert rtu_profile["status"] == "draft"


def test_rtu_layout_values_come_from_the_template(rtu_profile):
    """Layout values are filled ONLY from the RTU template, each citing it."""
    rules = rtu_profile["rules"]
    assert rules["TEXT-01"]["expected"] == {"font": "Times New Roman"}
    assert rules["TEXT-02"]["expected"] == {"size_pt": 12.0}
    assert rules["PAGE-01"]["expected"]["left_cm"] == 3.18
    for rid in ["PAGE-01", "PAGE-02", "TEXT-01", "TEXT-02", "TEXT-03", "TEXT-06", "HEAD-02"]:
        assert rules[rid]["guideline_ref"].startswith("rtu-template-2024"), rid
    # Things the template does not say stay TODO.
    for rid in ["PAGE-03", "TEXT-07", "FIG-04", "TAB-04", "LIST-01", "CITE-01"]:
        assert rules[rid]["guideline_ref"] == "TODO", rid


def test_rtu_source_rules_cite_the_slides(rtu_profile):
    refs = {rid: r["guideline_ref"] for rid, r in rtu_profile["rules"].items()}
    assert refs["REF-AI-01"] == "ai-slides p.4"
    assert refs["STRUCT-05"] == "ai-slides p.5"
    assert refs["CITE-04"] == "plag-slides p.6"
    assert refs["CITE-05"] == "plag-slides p.5"
    assert refs["REF-04"] == "plag-slides p.5"


def test_rtu_pending_rules_are_reported_as_not_checked(rtu_profile):
    report = run_sample("clean", rtu_profile)
    skipped = {s["rule_id"]: s["reason"] for s in report["skipped_rules"]}
    assert skipped["PAGE-03"] == REASON_PENDING
    assert REASON_NOT_IMPLEMENTED not in skipped.values()  # every rule exists now
    # clean.docx follows the DEMO profile, so the RTU margins differ.
    assert "PAGE-01" in rule_ids(report)


def test_todo_not_allowed_in_verified_profile():
    raw = _raw("rtu-fcsite-bachelor.yaml")
    raw["status"] = "verified"
    with pytest.raises(ValidationError, match="TODO"):
        ProfileModel.model_validate(raw)


def test_unknown_rule_id_rejected():
    raw = _raw("demo.yaml")
    raw["rules"]["PAGE-1"] = raw["rules"].pop("PAGE-01")
    with pytest.raises(ValidationError, match="unknown rule IDs"):
        ProfileModel.model_validate(raw)


def test_bad_expected_shape_rejected():
    raw = _raw("demo.yaml")
    raw["rules"]["PAGE-01"]["expected"] = {"top_cm": 2}  # missing the other sides
    with pytest.raises(ValidationError):
        ProfileModel.model_validate(raw)


def test_unknown_field_rejected():
    raw = _raw("demo.yaml")
    raw["colour"] = "blue"
    with pytest.raises(ValidationError):
        ProfileModel.model_validate(raw)


def test_second_university_needs_no_code_change():
    """A dummy profile with different values works through the same engine."""
    raw = copy.deepcopy(_raw("demo.yaml"))
    raw.update(id="dummy-uni", name="Dummy University", university="Dummy University")
    raw["rules"]["TEXT-01"]["expected"] = {"font": "Arial"}
    raw["rules"]["PAGE-01"]["expected"] = {
        "top_cm": 2.5, "bottom_cm": 2.5, "left_cm": 2.5, "right_cm": 2.5,
    }  # fmt: skip
    compiled = compile_profile_data(raw)
    found = rule_ids(run_sample("clean", compiled))
    assert "TEXT-01" in found  # clean.docx is Times New Roman, dummy wants Arial
    assert "PAGE-01" in found
