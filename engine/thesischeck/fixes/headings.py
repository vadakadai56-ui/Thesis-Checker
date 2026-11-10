"""Fixes for headings: formatting (HEAD-02), Word list numbering (HEAD-04),
capitals (HEAD-05) and starting chapters on a new page (HEAD-06).

Heading formatting is fixed in the heading STYLES and conflicting direct
formatting is removed. Capitals are switched on in the style — the heading is
never retyped.
"""

from __future__ import annotations

import re

from docx.oxml.ns import qn

from ..document_view import NumberingResolver, _related_root
from ..fixer import FixContext
from ..regions import norm
from ..rules.registry import fixer
from .ooxml import remove_attrs, remove_children, set_attrs, set_font, set_size, set_toggle

_JC = {
    "justified": "both",
    "left": "left",
    "center": "center",
    "centre": "center",
    "right": "right",
}


def _apply_heading_style(ctx: FixContext, style_id: str, want: dict) -> int:
    style = ctx.style_element(style_id)
    if style is None:
        return 0
    rpr, ppr = style.get_or_add_rPr(), style.get_or_add_pPr()
    if "font" in want:
        set_font(rpr, want["font"])
    if "size_pt" in want:
        set_size(rpr, round(float(want["size_pt"]) * 2))
    for key, tag in (("bold", "w:b"), ("caps", "w:caps")):
        if key in want:
            set_toggle(rpr, tag, bool(want[key]))
    if "align" in want:
        ppr.get_or_add_jc().set(qn("w:val"), _JC[want["align"]])
    spacing = {}
    if "before_pt" in want:
        spacing["before"] = round(float(want["before_pt"]) * 20)
    if "after_pt" in want:
        spacing["after"] = round(float(want["after_pt"]) * 20)
    if spacing:
        set_attrs(ppr.get_or_add_spacing(), **spacing)
    return 1


def _remove_direct(ctx: FixContext, index: int, want: dict) -> int:
    changes = 0
    for r in ctx.runs(index):
        rpr = r.find(qn("w:rPr"))
        if rpr is None:
            continue
        if "font" in want and rpr.find(qn("w:rFonts")) is not None:
            changes += remove_attrs(
                rpr.find(qn("w:rFonts")), "ascii", "hAnsi", "asciiTheme", "hAnsiTheme"
            )
        if "size_pt" in want:
            changes += remove_children(rpr, "w:sz", "w:szCs")
        if "bold" in want:
            changes += remove_children(rpr, "w:b", "w:bCs")
        if "caps" in want:
            changes += remove_children(rpr, "w:caps")
    ppr = ctx.element(index).find(qn("w:pPr"))
    if ppr is not None:
        if "align" in want:
            changes += remove_children(ppr, "w:jc")
        spacing = ppr.find(qn("w:spacing"))
        if spacing is not None:
            names = [n for k, n in (("before_pt", "before"), ("after_pt", "after")) if k in want]
            changes += remove_attrs(spacing, *names)
    return changes


@fixer("HEAD-02")
def fix_heading_format(ctx: FixContext) -> int:
    by_level = {str(k): v for k, v in ctx.expected.items()}
    changes = 0
    done: set[str] = set()
    for h in ctx.finding_paragraphs():
        want = by_level.get(str(h.heading_level), {})
        style_id = ctx.resolver.paragraph_style_id(ctx.element(h.index))
        if style_id and style_id not in done:
            done.add(style_id)
            changes += _apply_heading_style(ctx, style_id, want)
        changes += _remove_direct(ctx, h.index, want)
    return changes


@fixer("HEAD-04")
def fix_heading_numbering(ctx: FixContext) -> int:
    """Only for headings numbered by Word lists (typed numbers are never retyped)."""
    formats = list(ctx.expected.get("format", []))
    unnumbered = {norm(t) for t in ctx.expected.get("unnumbered", [])}
    numbering = NumberingResolver(_related_root(ctx.document, "numbering"))
    changes = 0
    done: set[tuple[str, int]] = set()
    for h in ctx.finding_paragraphs():
        if h.heading_number_source != "list" or h.numbering is None:
            continue
        if norm(h.text) in unnumbered:
            num_pr = ctx.element(h.index).get_or_add_pPr().get_or_add_numPr()
            num_pr.get_or_add_numId().set(qn("w:val"), "0")  # numId 0 = "no numbering"
            changes += 1
            continue
        key = (h.numbering.num_id, h.numbering.ilvl)
        level = h.heading_level or 1
        if key in done or level > len(formats):
            continue
        done.add(key)
        lvl = numbering.level(*key)
        if lvl is None:
            continue
        depth = len(re.findall(r"\d+", formats[level - 1]))
        text = ".".join(f"%{k}" for k in range(1, depth + 1)) + (
            "." if formats[level - 1].endswith(".") else ""
        )
        lvl_text = lvl.find(qn("w:lvlText"))
        if lvl_text is not None:
            lvl_text.set(qn("w:val"), text)
            changes += 1
    return changes


@fixer("HEAD-05")
def fix_heading_caps(ctx: FixContext) -> int:
    by_level = {str(k): v for k, v in ctx.expected.items()}
    changes = 0
    done: set[str] = set()
    for h in ctx.finding_paragraphs():
        if by_level.get(str(h.heading_level)) != "all_caps":
            continue
        style_id = ctx.resolver.paragraph_style_id(ctx.element(h.index))
        style = ctx.style_element(style_id)
        if style is not None and style_id not in done:
            done.add(style_id)
            set_toggle(style.get_or_add_rPr(), "w:caps", True)
            changes += 1
        for r in ctx.runs(h.index):
            rpr = r.find(qn("w:rPr"))
            caps = rpr.find(qn("w:caps")) if rpr is not None else None
            if caps is not None and caps.get(qn("w:val")) in ("0", "false", "off"):
                rpr.remove(caps)
                changes += 1
    return changes


@fixer("HEAD-06")
def fix_new_page(ctx: FixContext) -> int:
    for h in ctx.finding_paragraphs():
        set_toggle(ctx.element(h.index).get_or_add_pPr(), "w:pageBreakBefore", True)
    return len(ctx.finding_paragraphs())
