"""Fixes for the reference list (REF-03) and the table of contents (TOC-03)."""

from __future__ import annotations

from ..document_view import SINGLE_LINE
from ..fixer import FixContext
from ..rules.registry import fixer
from ..units import cm_to_twips
from .ooxml import remove_attrs, set_attrs, set_setting


@fixer("REF-03")
def fix_reference_format(ctx: FixContext) -> int:
    exp = ctx.expected
    for p in ctx.finding_paragraphs():
        ppr = ctx.element(p.index).get_or_add_pPr()
        if "hanging_indent_cm" in exp:
            hanging = round(cm_to_twips(float(exp["hanging_indent_cm"])))
            ind = ppr.get_or_add_ind()
            remove_attrs(ind, "firstLine", "firstLineChars", "hangingChars")
            set_attrs(ind, left=hanging, hanging=hanging)
        spacing = {}
        if "line_spacing" in exp:
            spacing.update(line=round(SINGLE_LINE * float(exp["line_spacing"])), lineRule="auto")
        if "before_pt" in exp:
            spacing["before"] = round(float(exp["before_pt"]) * 20)
        if "after_pt" in exp:
            spacing["after"] = round(float(exp["after_pt"]) * 20)
        if spacing:
            set_attrs(ppr.get_or_add_spacing(), **spacing)
    return len(ctx.finding_paragraphs())


@fixer("TOC-03")
def fix_toc_update(ctx: FixContext) -> int:
    """Ask Word to update all fields (incl. the contents) when the file is opened.

    Word then shows: "This document contains fields that may refer to other files.
    Update the fields in this document?" — answer Yes.
    """
    return int(set_setting(ctx.document.settings.element, "w:updateFields", True))
