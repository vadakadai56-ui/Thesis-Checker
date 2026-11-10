"""Annotated copy (BUILD_PROMPT §4e) — writes, like fixer.py, only to a copy.

    annotate(bytes, profile) -> {"bytes": <name>_annotated.docx, "report": …, …}

The annotated copy is the FIXED copy plus one Word comment (author "ThesisCheck")
on every problem that is left, e.g.

    [CITE-04] A quotation has no reference in the same or the next sentence.
    RTU rule: Directly copied … (plag-slides p.6). How to fix: Put the reference …

A comment is attached to the paragraph the finding points at. Findings without a
paragraph (page setup, page numbers, missing parts) go on the first paragraph of
the affected section, or of the document.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

from .api import _as_profile
from .document_view import _iter_blocks
from .docx_io import open_docx
from .fixer import _fixed_name, fix
from .model import Profile

AUTHOR = "ThesisCheck"
INITIALS = "TC"
ANNOTATE_RESULT_VERSION = 1


def comment_text(finding: dict[str, Any], short_name: str) -> str:
    return (
        f"[{finding['rule_id']}] {finding['message']} "
        f"{short_name} rule: {finding['rule_text']} ({finding['guideline_ref']}). "
        f"How to fix: {finding['how_to_fix']}"
    )


def _anchor_index(finding: dict[str, Any], paragraphs: list[Any], sections: dict[int, int]) -> int:
    """Which paragraph to attach the comment to."""
    location = finding["location"]
    index = location["paragraph_index"]
    if index is not None and index < len(paragraphs):
        return index
    if location["section_index"] is not None and location["section_index"] in sections:
        return sections[location["section_index"]]
    return 0


def _runs_for(paragraph: Paragraph):
    """The runs to anchor a comment on; adds an empty run if the paragraph has none.

    An empty run adds no text, so the document's words stay exactly the same.
    """
    runs = paragraph.runs
    return runs if runs else [paragraph.add_run("")]


def annotate(
    data: bytes,
    profile: Profile | dict[str, Any],
    file_name: str = "document.docx",
    now: datetime | None = None,
) -> dict[str, Any]:
    prof = _as_profile(profile)
    fixed = fix(data, prof, file_name=file_name, now=now)
    document = open_docx(fixed["bytes"])
    p_elements = [b.p_el for b in _iter_blocks(document.element.body, {"tables": []})]
    body = document._body
    # First paragraph of each Word section (for findings about a whole section).
    section_starts: dict[int, int] = {}
    section = 0
    for i, p_el in enumerate(p_elements):
        section_starts.setdefault(section, i)
        ppr = p_el.find(qn("w:pPr"))
        if ppr is not None and ppr.find(qn("w:sectPr")) is not None:  # a section ends here
            section += 1

    short_name = prof.extra.get("short_name") or prof.name
    findings = fixed["report"]["findings"]
    for finding in findings:
        index = _anchor_index(finding, p_elements, section_starts)
        paragraph = Paragraph(p_elements[index], body)
        document.add_comment(
            _runs_for(paragraph),
            text=comment_text(finding, short_name),
            author=AUTHOR,
            initials=INITIALS,
        )

    out = io.BytesIO()
    document.save(out)
    report = {**fixed["report"], "file_name": _fixed_name(file_name, "annotated")}
    return {
        "version": ANNOTATE_RESULT_VERSION,
        "kind": "annotated",
        "file_name": _fixed_name(file_name, "annotated"),
        "bytes": out.getvalue(),
        "report": report,
        "before": fixed["before"],
        "fixed_findings": fixed["fixed_findings"],
        "fixes": fixed["fixes"],
        "comments": len(findings),
    }
