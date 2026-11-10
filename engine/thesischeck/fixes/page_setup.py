"""Fixes for page setup: margins (PAGE-01), paper size (PAGE-02), gutter (PAGE-04)."""

from __future__ import annotations

from docx.oxml.ns import qn

from ..fixer import FixContext
from ..rules.registry import fixer
from ..units import PAPER_SIZES_TWIPS, cm_to_twips
from .ooxml import set_attrs, set_setting


@fixer("PAGE-01")
def fix_margins(ctx: FixContext) -> int:
    exp = {
        side: round(cm_to_twips(ctx.expected[f"{side}_cm"]))
        for side in ("top", "bottom", "left", "right")
    }
    for index in ctx.finding_sections():
        margins = dict(exp)
        if ctx.view.sections[index].is_landscape:
            # Turn the margins with the page (clockwise), as Word does.
            margins = {
                "top": exp["left"],
                "right": exp["top"],
                "bottom": exp["right"],
                "left": exp["bottom"],
            }
        set_attrs(ctx.sect_pr(index).get_or_add_pgMar(), **margins)
    return len(ctx.finding_sections())


@fixer("PAGE-02")
def fix_paper(ctx: FixContext) -> int:
    width, height = PAPER_SIZES_TWIPS[ctx.expected["paper"]]
    for index in ctx.finding_sections():
        pg_sz = ctx.sect_pr(index).get_or_add_pgSz()
        landscape = ctx.view.sections[index].is_landscape
        set_attrs(pg_sz, w=height if landscape else width, h=width if landscape else height)
        pg_sz.attrib.pop(qn("w:code"), None)  # the printer paper code would contradict
    return len(ctx.finding_sections())


@fixer("PAGE-04")
def fix_gutter(ctx: FixContext) -> int:
    changes = 0
    gutter = round(cm_to_twips(ctx.expected.get("gutter_cm", 0)))
    for index in ctx.finding_sections():
        set_attrs(ctx.sect_pr(index).get_or_add_pgMar(), gutter=gutter)
        changes += 1
    want_mirror = bool(ctx.expected.get("mirror_margins", False))
    if ctx.view.mirror_margins != want_mirror:
        changes += set_setting(ctx.document.settings.element, "w:mirrorMargins", want_mirror)
    return changes
