"""The official RTU template must pass the RTU profile, and the profile's values must
match the template's own styles (catches typos when copying values by hand).

The template is not committed (see docs/sources/README.md); put it at
engine/tests/private/RTU_k_thesis_template_2024.dotx to run these tests.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from conftest import rule_ids, run
from thesischeck.document_view import build_view
from thesischeck.docx_io import open_docx
from thesischeck.units import twips_to_cm

TEMPLATE = Path(__file__).parent / "private" / "RTU_k_thesis_template_2024.dotx"
pytestmark = pytest.mark.skipif(not TEMPLATE.exists(), reason="RTU template not present")


def template_as_docx() -> bytes:
    """A .dotx is a .docx with a different content type; swap it so Word/python-docx open it."""
    out = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == "[Content_Types].xml":
                data = data.replace(b".template.main+xml", b".document.main+xml")
            dst.writestr(info, data)
    return out.getvalue()


# What the untouched official template is EXPECTED to get. Anything else is a bug
# in ThesisCheck (or a profile value that doesn't match the template).
KNOWN_TEMPLATE_FINDINGS = [
    # The "where Qg – …" lines under the example formula have no first-line indent
    # (style Normal, not Text). Asked the owner whether to treat them as exceptions.
    ("TEXT-06", "where Qg – volume of material required p"),
    ("TEXT-06", "q – material consumption rate, kg/pcs;"),
    ("TEXT-06", "Ng – annual production volume, pcs."),
    # The template's last section (references + appendixes) has an empty footer,
    # so those pages have no page numbers. Asked the owner if that is intended.
    ("PGNUM-02", "list of references"),
    # The template has no "Tools used in writing this thesis" paragraph (info).
    ("STRUCT-05", "introduction"),
    # The title page still has "<…>" placeholders and no real year — correct for
    # an unfilled template.
    ("TITLE-01", "RIGA TECHNICAL UNIVERSITY"),  # missing "RIGA <year>"
    ("TITLE-01", "RIGA TECHNICAL UNIVERSITY"),  # placeholders left in
]


def test_template_gets_only_the_known_findings(rtu_profile):
    report = run(template_as_docx(), rtu_profile)
    found = sorted((f["rule_id"], f["location"]["snippet"][:40]) for f in report["findings"])
    assert found == sorted(KNOWN_TEMPLATE_FINDINGS)
    assert report["score"]["capped"] is True  # placeholders = a blocking title-page problem


def test_profile_values_match_template_styles(rtu_profile):
    view = build_view(open_docx(template_as_docx()))
    rules = rtu_profile["rules"]

    margins = rules["PAGE-01"]["expected"]
    for section in view.sections:
        assert round(twips_to_cm(section.margin_left), 2) == margins["left_cm"]
        assert round(twips_to_cm(section.margin_top), 2) == margins["top_cm"]
        assert section.gutter == 0
    assert view.mirror_margins is False

    text_paragraphs = [p for p in view.paragraphs if p.style_name == "Text" and p.runs]
    assert text_paragraphs
    for p in text_paragraphs:
        for r in p.runs:
            if r.text.strip():
                assert r.font_ascii == rules["TEXT-01"]["expected"]["font"]
                assert r.size_pt == rules["TEXT-02"]["expected"]["size_pt"]

    levels = {p.style_name: p.heading_level for p in view.headings}
    assert levels["Level-1-heading"] == 1
    assert levels["Level-2-heading"] == 2
    assert levels["Level-3-heading"] == 3


def test_without_non_body_styles_code_would_be_flagged(rtu_profile):
    """Shows why `text.non_body_styles` exists: the template's Code style is Arial Narrow."""
    profile = {**rtu_profile, "text": {"non_body_styles": []}}
    found = rule_ids(run(template_as_docx(), profile))
    assert "TEXT-01" in found and "TEXT-02" in found
