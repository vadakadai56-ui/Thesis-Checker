"""Fixes for page numbers: add them (PGNUM-01), put them in the right place and
format (PGNUM-02), hide/not count them on the title page (PGNUM-03)."""

from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

from ..fixer import FixContext
from ..rules.registry import fixer
from .ooxml import append_field, has_page_field, pg_num_type, remove_page_fields

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "centre": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}
_FORMATS = {"arabic": "decimal", "roman": "lowerRoman"}


def _position(ctx: FixContext) -> tuple[str, str]:
    """('bottom', 'center') from the PGNUM-02 setting, or bottom centre by default."""
    cfg = ctx.profile.rules.get("PGNUM-02")
    position = (cfg.expected or {}).get("position", "bottom_center") if cfg else "bottom_center"
    place, align = position.split("_")
    return place, align


def _part(section, place: str):
    return section.footer if place == "bottom" else section.header


def _page_paragraph(part):
    return next((p for p in part.paragraphs if has_page_field(p._p)), None)


def _add_number(part, align: str) -> None:
    """Add a page number to a header/footer (in an empty paragraph if there is one)."""
    empty = [p for p in part.paragraphs if not p.text.strip() and not has_page_field(p._p)]
    paragraph = empty[0] if empty else part.add_paragraph()
    paragraph.alignment = _ALIGN[align]
    append_field(paragraph._p, "PAGE")


@fixer("PGNUM-01")
def fix_add_page_numbers(ctx: FixContext) -> int:
    place, align = _position(ctx)
    changes = 0
    for i, section in enumerate(ctx.document.sections):
        part = _part(section, place)
        # Section 1, and any later section with its own footer, needs the number;
        # the others "link to previous" and show it automatically.
        if (i == 0 or not part.is_linked_to_previous) and _page_paragraph(part) is None:
            _add_number(part, align)
            changes += 1
    return changes


def _clear_tabs_before(paragraph) -> None:
    """Drop tab characters used to push the number sideways (they'd fight alignment)."""
    for r in paragraph._p.iter(qn("w:r")):
        if r.find(qn("w:fldChar")) is not None:
            break
        for tab in r.findall(qn("w:tab")) + r.findall(qn("w:ptab")):
            r.remove(tab)


@fixer("PGNUM-02")
def fix_page_number_position(ctx: FixContext) -> int:
    place, align = _position(ctx)
    other = "top" if place == "bottom" else "bottom"
    want_format = _FORMATS[(ctx.expected or {}).get("format", "arabic")]
    changes = 0
    for index in ctx.finding_sections():
        section = ctx.document.sections[index]
        paragraph = _page_paragraph(_part(section, place))
        if paragraph is None:
            wrong_edge = _page_paragraph(_part(section, other))
            if wrong_edge is not None:
                remove_page_fields(wrong_edge._p)
            _add_number(_part(section, place), align)
        else:
            _clear_tabs_before(paragraph)
            paragraph.alignment = _ALIGN[align]
        current = section._sectPr.find(qn("w:pgNumType"))
        fmt = current.get(qn("w:fmt")) if current is not None else None
        if (fmt or "decimal") != want_format:
            pg_num_type(section._sectPr).set(qn("w:fmt"), want_format)
        changes += 1
    return changes


@fixer("PGNUM-03")
def fix_title_page_number(ctx: FixContext) -> int:
    changes = 0
    sections = ctx.document.sections
    first = sections[0]
    view_first = ctx.view.sections[0]
    shown = any("shows a page number" in f["message"] for f in ctx.findings)
    if shown:
        first.different_first_page_header_footer = True
        for part in (first.first_page_footer, first.first_page_header):
            if not part.is_linked_to_previous:
                for paragraph in part.paragraphs:
                    changes += remove_page_fields(paragraph._p)
        changes += 1
    if any("counted" in f["message"] or "restarts" in f["message"] for f in ctx.findings):
        want_counted = bool((ctx.expected or {}).get("title_page_counted"))
        if want_counted:
            for section in sections[1:2]:
                pg = section._sectPr.find(qn("w:pgNumType"))
                if pg is not None:
                    pg.attrib.pop(qn("w:start"), None)
            if view_first.page_number_start == 0:
                pg_num_type(first._sectPr).attrib.pop(qn("w:start"), None)
        else:
            # Title page = page 0, so the next page is page 1.
            pg_num_type(first._sectPr).set(qn("w:start"), "0")
        changes += 1
    return changes
