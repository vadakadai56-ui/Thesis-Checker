"""TEXT-01 (body font) and TEXT-02 (body size), incl. the style resolution chain."""

from __future__ import annotations

import pytest
from docx.shared import Pt

from conftest import rule_ids, run_doc, run_sample
from thesischeck.document_view import build_view
from tools.make_samples import make_clean, make_theme_font_only


@pytest.mark.parametrize("rule_id", ["TEXT-01", "TEXT-02"])
def test_clean_has_no_finding(rule_id, demo_profile):
    assert rule_id not in rule_ids(run_sample("clean", demo_profile))


@pytest.mark.parametrize("rule_id", ["TEXT-01", "TEXT-02"])
def test_bad_sample_gives_exactly_that_finding(rule_id, demo_profile):
    assert rule_ids(run_sample(rule_id, demo_profile)) == [rule_id]


def test_text01_message_and_location(demo_profile):
    (finding,) = run_sample("TEXT-01", demo_profile)["findings"]
    assert finding["found"] == "Arial"
    assert finding["expected"] == "Times New Roman"
    assert finding["location"]["snippet"].startswith("The aim of the work")
    assert finding["location"]["heading_path"] == ["Introduction"]


def test_text02_message(demo_profile):
    (finding,) = run_sample("TEXT-02", demo_profile)["findings"]
    assert finding["found"] == "14 pt"
    assert finding["expected"] == "12 pt"


def test_font_falls_back_to_theme_body_font(demo_profile):
    """With no font in the Normal style, Word uses docDefaults → theme minor font."""
    doc = make_theme_font_only()
    view = build_view(doc)
    theme_body_font = view.theme_fonts["minor"]
    report = run_doc(doc, demo_profile)
    text01 = [f for f in report["findings"] if f["rule_id"] == "TEXT-01"]
    assert text01, "theme font should be reported as wrong"
    assert {f["found"] for f in text01} == {theme_body_font}


def test_font_inherited_through_based_on_chain(demo_profile):
    """A custom style based on Normal inherits Normal's font: no finding."""
    doc = make_clean()
    from docx.enum.style import WD_STYLE_TYPE

    style = doc.styles.add_style("Thesis Body", WD_STYLE_TYPE.PARAGRAPH)
    style.base_style = doc.styles["Normal"]
    target = next(p for p in doc.paragraphs if p.text.startswith("The aim"))
    target.style = style
    assert "TEXT-01" not in rule_ids(run_doc(doc, demo_profile))

    style.font.name = "Arial"  # now the custom style overrides the font
    assert rule_ids(run_doc(doc, demo_profile)) == ["TEXT-01"]


def test_title_page_and_headings_are_not_body_text(demo_profile):
    """Title page (before first heading) and headings are not checked by TEXT-01."""
    doc = make_clean()
    doc.paragraphs[0].runs[0].font.name = "Arial"  # the Title
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            for r in p.runs:
                r.font.name = "Arial"
    found = rule_ids(run_doc(doc, demo_profile))
    assert "TEXT-01" not in found
    assert "HEAD-02" in found  # heading fonts are HEAD-02's job


def test_tracked_deletion_is_ignored(demo_profile):
    """Text inside a tracked deletion is checked 'as if accepted' (i.e. ignored)."""
    from docx.oxml import parse_xml

    doc = make_clean()
    target = next(p for p in doc.paragraphs if p.text.startswith("The aim"))
    target._p.append(
        parse_xml(
            '<w:del xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'w:id="1" w:author="x"><w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>'
            "</w:rPr><w:delText> deleted</w:delText></w:r></w:del>"
        )
    )
    assert rule_ids(run_doc(doc, demo_profile)) == []


def test_latvian_letters_use_hansi_font(demo_profile):
    """Characters like ā/č are drawn with the hAnsi font, so that slot is checked too."""
    from docx.oxml.ns import qn

    doc = make_clean()
    target = next(p for p in doc.paragraphs if p.text.startswith("The aim"))
    run = target.add_run(" Rīga")
    rfonts = run._r.get_or_add_rPr().get_or_add_rFonts()
    rfonts.set(qn("w:hAnsi"), "Arial")  # ascii stays Times New Roman
    (finding,) = run_doc(doc, demo_profile)["findings"]
    assert finding["rule_id"] == "TEXT-01"
    assert finding["found"] == "Arial"


def test_profile_non_body_styles_are_skipped(demo_profile):
    """Styles listed in the profile's text.non_body_styles are not body text."""
    from docx.enum.style import WD_STYLE_TYPE

    doc = make_clean()
    code = doc.styles.add_style("Code", WD_STYLE_TYPE.PARAGRAPH)
    code.base_style = doc.styles["Normal"]
    code.font.name = "Arial Narrow"
    code.font.size = Pt(11)
    after = next(p for p in doc.paragraphs if p.text.startswith("Tools used"))
    after.insert_paragraph_before("print('hello')", style=code)
    assert sorted(rule_ids(run_doc(doc, demo_profile))) == ["TEXT-01", "TEXT-02"]

    profile = {**demo_profile, "text": {"non_body_styles": ["code"]}}  # case-insensitive
    assert rule_ids(run_doc(doc, profile)) == []
