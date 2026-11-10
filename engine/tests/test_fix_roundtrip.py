"""Auto-fix and annotated copy (BUILD_PROMPT §4d, §4e, §15 "Roundtrip").

For every sample:
  * the score after fixing is at least the score before,
  * the input bytes are untouched (same SHA-256),
  * the output opens, and its words are exactly the original words,
  * the annotated copy has one valid Word comment per remaining finding.
For every auto-fixable rule: fixing its sample removes that rule's findings.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm

from conftest import FIXED_NOW, SAMPLES_DIR, rule_ids, run, sample_bytes
from thesischeck import annotate, fix
from thesischeck.document_view import build_view
from thesischeck.docx_io import open_docx, safe_parse
from thesischeck.model import EngineError
from thesischeck.rule_ids import ALL_RULE_IDS
from thesischeck.rules.registry import _FIXERS
from tools.make_samples import build_document, clean_blocks, make_clean, to_bytes

SAMPLES = sorted(p.stem for p in SAMPLES_DIR.glob("*.docx"))
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _words(data: bytes) -> list[str]:
    return [w for p in build_view(open_docx(data)).paragraphs for w in p.text.split()]


def _fix(data: bytes, profile: dict, name: str = "x.docx") -> dict:
    return fix(data, profile, file_name=name, now=FIXED_NOW)


@pytest.mark.parametrize("name", SAMPLES)
def test_fix_roundtrip(name, demo_profile):
    data = sample_bytes(name)
    sha_before = hashlib.sha256(data).hexdigest()
    result = _fix(data, demo_profile, f"{name}.docx")
    assert hashlib.sha256(data).hexdigest() == sha_before  # input untouched
    assert result["file_name"] == f"{name}_fixed.docx"
    assert result["report"]["score"]["value"] >= result["before"]["score"]["value"]
    open_docx(result["bytes"])  # the fixed copy opens
    assert _words(result["bytes"]) == _words(data)  # not one word changed


FIXABLE = [r for r in ALL_RULE_IDS if r in _FIXERS]


def test_fixable_rules_match_build_prompt():
    """§5 'Fix?' column (HEAD-04 only for Word-list numbering)."""
    assert set(FIXABLE) == {
        "PAGE-01", "PAGE-02", "PAGE-04", "TEXT-01", "TEXT-02", "TEXT-03", "TEXT-04",
        "TEXT-05", "TEXT-06", "TEXT-07", "TEXT-08", "HEAD-02", "HEAD-04", "HEAD-05",
        "HEAD-06", "PGNUM-01", "PGNUM-02", "PGNUM-03", "TOC-03", "REF-03",
    }  # fmt: skip


@pytest.mark.parametrize("rule_id", [r for r in FIXABLE if r != "HEAD-04"])
def test_fix_removes_the_rules_findings(rule_id, demo_profile):
    before = run(sample_bytes(rule_id), demo_profile)
    assert all(f["fixable"] for f in before["findings"])
    result = _fix(sample_bytes(rule_id), demo_profile)
    assert rule_ids(result["report"]) == []
    assert result["report"]["score"]["value"] == 100
    assert all(f["fixed"] for f in result["fixed_findings"])
    assert [x["rule_id"] for x in result["fixes"]] == [rule_id]


def test_typed_heading_numbers_are_never_retyped(demo_profile):
    """HEAD-04 with numbers typed by hand: not fixable, left for the student."""
    (finding,) = run(sample_bytes("HEAD-04"), demo_profile)["findings"]
    assert finding["fixable"] is False
    assert rule_ids(_fix(sample_bytes("HEAD-04"), demo_profile)["report"]) == ["HEAD-04"]


def _numbered_heading_doc():
    """Headings numbered by a Word list whose level-1 format is '1' (no full stop),
    plus an 'Introduction' heading that wrongly has a number."""
    # Remove the typed numbers ("1. Theory" -> "Theory"); Word's list will number them.
    blocks = [
        ("h1", b[1].split(". ", 1)[1]) if b[0] == "h1" and b[1][0].isdigit() else b
        for b in clean_blocks()
    ]
    doc = build_document(blocks)
    numbering = doc.part.numbering_part.element
    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), "90")
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    for tag, val in (("w:start", "1"), ("w:numFmt", "decimal"), ("w:lvlText", "%1")):
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        lvl.append(el)
    abstract.append(lvl)
    numbering.insert(0, abstract)
    num = OxmlElement("w:num")
    num.set(qn("w:numId"), "90")
    ref = OxmlElement("w:abstractNumId")
    ref.set(qn("w:val"), "90")
    num.append(ref)
    numbering.append(num)
    for p in doc.paragraphs:
        if p.style.name == "Heading 1":
            num_pr = p._p.get_or_add_pPr().get_or_add_numPr()
            num_pr.get_or_add_ilvl().val = 0
            num_pr.get_or_add_numId().val = 90
    return doc


def test_list_numbered_headings_are_fixed(demo_profile):
    data = to_bytes(_numbered_heading_doc())
    head04 = [f for f in run(data, demo_profile)["findings"] if f["rule_id"] == "HEAD-04"]
    assert head04 and all(f["fixable"] for f in head04)
    messages = " ".join(f["message"] for f in head04)
    assert "should not be numbered" in messages and "doesn't match the format" in messages
    after = _fix(data, demo_profile)["report"]
    assert "HEAD-04" not in rule_ids(after)


def test_title_page_counted_is_fixed(demo_profile):
    doc = make_clean()
    pg = doc.sections[1]._sectPr.find(qn("w:pgNumType"))
    pg.getparent().remove(pg)  # numbering no longer restarts after the title page
    data = to_bytes(doc)
    assert rule_ids(run(data, demo_profile)) == ["PGNUM-03"]
    assert rule_ids(_fix(data, demo_profile)["report"]) == []


def test_landscape_margins_fixed_rotated(demo_profile):
    from docx.shared import Cm

    from tools.make_samples import make_landscape_rotated

    doc = make_landscape_rotated()
    doc.sections[-1].left_margin = Cm(5)
    data = to_bytes(doc)
    assert rule_ids(run(data, demo_profile)) == ["PAGE-01"]
    fixed = _fix(data, demo_profile)
    assert rule_ids(fixed["report"]) == []
    section = open_docx(fixed["bytes"]).sections[-1]
    assert round(section.top_margin.cm, 2) == 3.0  # the left margin, turned to the top


def test_all_problems_at_once(demo_profile):
    """Every fixable problem in one document: fixed together, words unchanged."""
    doc = build_document([*clean_blocks(), ("empty",), ("empty",)])
    for p in doc.paragraphs:
        if p.text.startswith("The aim"):
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.first_line_indent = Cm(0)
            p.runs[0].font.name = "Arial"
    doc.sections[1].left_margin = Cm(2.5)
    data = to_bytes(doc)
    before = run(data, demo_profile)
    result = _fix(data, demo_profile)
    assert result["report"]["score"]["value"] > before["score"]["value"]
    assert _words(result["bytes"]) == _words(data)


def test_safety_net_refuses_changed_text(demo_profile, monkeypatch):
    """If a fix ever changed the words, fix() must refuse instead of returning it."""

    def evil(ctx):
        ctx.element(ctx.finding_paragraphs()[0].index).find(f"{W}r/{W}t").text = "CHANGED"
        return 1

    monkeypatch.setitem(_FIXERS, "TEXT-03", evil)
    with pytest.raises(EngineError) as err:
        _fix(sample_bytes("TEXT-03"), demo_profile)
    assert err.value.code == "INTERNAL"


# ---------------------------------------------------------------- annotated copy


def _comments(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if "word/comments.xml" not in zf.namelist():
            return []
        root = safe_parse(zf.read("word/comments.xml"))  # valid XML
        document = zf.read("word/document.xml")
    texts = ["".join(t.text or "" for t in c.iter(f"{W}t")) for c in root.iter(f"{W}comment")]
    assert document.count(b"<w:commentRangeStart") == len(texts)  # each one is anchored
    return texts


@pytest.mark.parametrize("name", SAMPLES)
def test_annotated_copy(name, demo_profile):
    data = sample_bytes(name)
    result = annotate(data, demo_profile, file_name=f"{name}.docx", now=FIXED_NOW)
    assert result["file_name"] == f"{name}_annotated.docx"
    comments = _comments(result["bytes"])
    findings = result["report"]["findings"]
    assert len(comments) == len(findings) == result["comments"]
    for text, finding in zip(comments, findings, strict=True):
        assert text.startswith(f"[{finding['rule_id']}] {finding['message']}")
        assert "DEMO rule:" in text and "How to fix:" in text
    assert _words(result["bytes"]) == _words(data)


def test_annotated_comment_author(demo_profile):
    result = annotate(sample_bytes("CITE-04"), demo_profile, now=FIXED_NOW)
    doc = open_docx(result["bytes"])
    (comment,) = list(doc.comments)
    assert comment.author == "ThesisCheck"
    assert comment.text.startswith("[CITE-04]")


# ---------------------------------------------------------------- LibreOffice

SOFFICE = shutil.which("soffice")


@pytest.mark.skipif(SOFFICE is None, reason="LibreOffice not installed")
@pytest.mark.parametrize("name", ["CITE-04", "TITLE-01", "PGNUM-01"])
def test_libreoffice_opens_fixed_and_annotated_files(name, demo_profile, tmp_path):
    """Convert with LibreOffice; the comments must survive as ODF annotations."""
    result = annotate(sample_bytes(name), demo_profile, now=FIXED_NOW)
    path = tmp_path / f"{name}_annotated.docx"
    path.write_bytes(result["bytes"])
    odt = _convert(path, tmp_path)
    with zipfile.ZipFile(odt) as zf:
        content = zf.read("content.xml")
    assert (
        content.count(b"<office:annotation ") + content.count(b"<office:annotation>")
        == result["comments"]
    )


def _convert(path: Path, out_dir: Path) -> Path:
    subprocess.run(
        [SOFFICE, "--headless", "--norestore", f"-env:UserInstallation=file://{out_dir}/lo",
         "--convert-to", "odt", "--outdir", str(out_dir), str(path)],
        check=True, capture_output=True, timeout=180,
    )  # fmt: skip
    odt = out_dir / f"{path.stem}.odt"
    assert odt.exists(), "LibreOffice could not open the file"
    return odt
