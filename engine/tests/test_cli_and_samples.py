"""The CLI, the report contract, and that committed samples match the generator."""

from __future__ import annotations

import json

import pytest

from conftest import SAMPLES_DIR, run_sample
from thesischeck.__main__ import main
from tools.compile_profiles import compile_all
from tools.make_samples import SAMPLES, generate


@pytest.fixture
def profiles_dir(tmp_path):
    out = tmp_path / "profiles"
    compile_all(out=out)
    return out


def test_cli_clean_docx_has_zero_findings(profiles_dir, capsys):
    code = main(["check", str(SAMPLES_DIR / "clean.docx"), "--profiles-dir", str(profiles_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "0 finding(s)" in out
    assert "not a plagiarism or AI-text detector" in out


def test_cli_json_output(profiles_dir, capsys):
    args = ["check", str(SAMPLES_DIR / "TEXT-01.docx"), "--json"]
    code = main([*args, "--profiles-dir", str(profiles_dir)])
    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert [f["rule_id"] for f in report["findings"]] == ["TEXT-01"]


def test_cli_rejects_bad_file(profiles_dir, tmp_path, capsys):
    bad = tmp_path / "x.docx"
    bad.write_bytes(b"hello")
    assert main(["check", str(bad), "--profiles-dir", str(profiles_dir)]) == 3
    assert "NOT_DOCX" in capsys.readouterr().err


def test_report_contract(demo_profile):
    """Fields from BUILD_PROMPT §6b/§6c are all present."""
    report = run_sample("TEXT-01", demo_profile)
    assert set(report) == {
        "version", "engine_version", "document_sha256", "file_name", "profile",
        "created_at", "stats", "findings", "score", "skipped_rules",
    }  # fmt: skip
    assert report["profile"] == {"id": "demo", "version": 1, "status": "draft"}
    assert set(report["stats"]) == {"paragraphs", "pages_estimate", "words"}
    (finding,) = report["findings"]
    assert set(finding) == {
        "version", "id", "rule_id", "category", "severity", "message", "rule_text",
        "guideline_ref", "location", "expected", "found", "fixable", "fixed", "how_to_fix",
    }  # fmt: skip
    assert set(finding["location"]) == {
        "part", "paragraph_index", "section_index", "page_estimate", "heading_path", "snippet",
    }  # fmt: skip
    assert finding["id"] == "TEXT-01#1"
    assert finding["category"] == "text"
    json.dumps(report)  # must be JSON-serialisable for the browser worker


def test_committed_samples_are_up_to_date(tmp_path):
    """If this fails, run `python tools/make_samples.py` and commit the samples."""
    generate(tmp_path)
    for name in SAMPLES:
        fresh = (tmp_path / f"{name}.docx").read_bytes()
        committed = (SAMPLES_DIR / f"{name}.docx").read_bytes()
        assert fresh == committed, name
