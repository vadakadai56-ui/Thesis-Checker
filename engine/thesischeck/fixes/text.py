"""Fixes for body text: font (TEXT-01), size (TEXT-02), line spacing (TEXT-03),
alignment (TEXT-04), spacing (TEXT-05), first-line indent (TEXT-06), direct
formatting (TEXT-07) and empty spacing paragraphs (TEXT-08).

Fonts and sizes are fixed in the paragraph's STYLE (so every paragraph using it is
right) and conflicting direct formatting is removed. Paragraph layout (spacing,
alignment, indent) is set on the affected paragraphs only, because changing e.g.
"Normal" would also move headings and captions that are based on it.
"""

from __future__ import annotations

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from ..document_view import SINGLE_LINE, _run_text
from ..fixer import FixContext
from ..rules.registry import fixer
from ..units import cm_to_twips
from .ooxml import drop_if_empty, remove_attrs, remove_children, set_attrs, set_font, set_size

_FONT_ATTRS = ("ascii", "hAnsi", "asciiTheme", "hAnsiTheme")


def _style_rpr(ctx: FixContext, style_id: str | None):
    style = ctx.style_element(style_id)
    if style is not None:
        return style.get_or_add_rPr()
    # No paragraph style at all: the document defaults apply.
    return (
        ctx.document.styles.element.find(qn("w:docDefaults"))
        .find(qn("w:rPrDefault"))
        .find(qn("w:rPr"))
    )


def _font_ok(run_view, expected: str) -> bool:
    return all(f.casefold() == expected.casefold() for f in run_view.fonts_used())


def _fix_run_property(ctx: FixContext, kind: str) -> int:
    """kind = 'font' or 'size'."""
    resolver = ctx.resolver
    expected = ctx.expected["font"] if kind == "font" else float(ctx.expected["size_pt"])
    changes = 0
    styles_done: set[str | None] = set()
    for p in ctx.finding_paragraphs():
        el = ctx.element(p.index)
        style_id = resolver.paragraph_style_id(el)
        # 1. Fix the style if the style itself gives the wrong value.
        if style_id not in styles_done:
            styles_done.add(style_id)
            base = resolver.resolve_run(OxmlElement("w:r"), style_id, "x")
            wrong = (
                (base.font_ascii.casefold() != expected.casefold())
                if kind == "font"
                else (abs(base.size_pt - expected) > 0.25)
            )
            if wrong:
                rpr = _style_rpr(ctx, style_id)
                set_font(rpr, expected) if kind == "font" else set_size(rpr, round(expected * 2))
                changes += 1
        # 2. Remove direct formatting that overrides it; 3. last resort for character styles.
        for r in ctx.runs(p.index):
            text = _run_text(r)
            if not text.strip():
                continue
            view = resolver.resolve_run(r, style_id, text)
            ok = (
                _font_ok(view, expected) if kind == "font" else abs(view.size_pt - expected) <= 0.25
            )
            if ok:
                continue
            rpr = r.find(qn("w:rPr"))
            if rpr is not None:
                if kind == "font" and rpr.find(qn("w:rFonts")) is not None:
                    changes += remove_attrs(rpr.find(qn("w:rFonts")), *_FONT_ATTRS)
                    drop_if_empty(rpr.find(qn("w:rFonts")))
                elif kind == "size":
                    changes += remove_children(rpr, "w:sz", "w:szCs")
            view = resolver.resolve_run(r, style_id, text)
            ok = (
                _font_ok(view, expected) if kind == "font" else abs(view.size_pt - expected) <= 0.25
            )
            if not ok:  # a character style sets it: override on the run itself
                rpr = r.get_or_add_rPr()
                set_font(rpr, expected) if kind == "font" else set_size(rpr, round(expected * 2))
                changes += 1
    return changes


@fixer("TEXT-01")
def fix_font(ctx: FixContext) -> int:
    return _fix_run_property(ctx, "font")


@fixer("TEXT-02")
def fix_size(ctx: FixContext) -> int:
    return _fix_run_property(ctx, "size")


@fixer("TEXT-03")
def fix_line_spacing(ctx: FixContext) -> int:
    line = round(SINGLE_LINE * float(ctx.expected["line_spacing"]))
    for p in ctx.finding_paragraphs():
        spacing = ctx.element(p.index).get_or_add_pPr().get_or_add_spacing()
        set_attrs(spacing, line=line, lineRule="auto")
    return len(ctx.finding_paragraphs())


_JC = {"justified": "both", "left": "left", "center": "center", "right": "right"}


@fixer("TEXT-04")
def fix_alignment(ctx: FixContext) -> int:
    for p in ctx.finding_paragraphs():
        ctx.element(p.index).get_or_add_pPr().get_or_add_jc().set(
            qn("w:val"), _JC[ctx.expected["alignment"]]
        )
    return len(ctx.finding_paragraphs())


@fixer("TEXT-05")
def fix_spacing(ctx: FixContext) -> int:
    before = round(float(ctx.expected.get("before_pt", 0)) * 20)
    after = round(float(ctx.expected.get("after_pt", 0)) * 20)
    for p in ctx.finding_paragraphs():
        spacing = ctx.element(p.index).get_or_add_pPr().get_or_add_spacing()
        remove_attrs(spacing, "beforeAutospacing", "afterAutospacing", "beforeLines", "afterLines")
        set_attrs(spacing, before=before, after=after)
    return len(ctx.finding_paragraphs())


@fixer("TEXT-06")
def fix_first_line(ctx: FixContext) -> int:
    first = round(cm_to_twips(float(ctx.expected["first_line_cm"])))
    for p in ctx.finding_paragraphs():
        ind = ctx.element(p.index).get_or_add_pPr().get_or_add_ind()
        remove_attrs(ind, "hanging", "hangingChars", "firstLineChars")
        set_attrs(ind, firstLine=first)
    return len(ctx.finding_paragraphs())


# RunView.direct names -> the XML elements that hold them in <w:rPr>.
_DIRECT_TAGS = {
    "size_pt": ("w:sz", "w:szCs"),
    "bold": ("w:b", "w:bCs"),
    "italic": ("w:i", "w:iCs"),
    "underline": ("w:u",),
    "color": ("w:color",),
    "caps": ("w:caps",),
    "highlight": ("w:highlight",),
}


@fixer("TEXT-07")
def fix_direct_formatting(ctx: FixContext) -> int:
    changes = 0
    for p in ctx.finding_paragraphs():
        for run_view, r in zip(p.runs, ctx.runs(p.index), strict=False):
            rpr = r.find(qn("w:rPr"))
            if rpr is None:
                continue
            for name in run_view.direct:
                if name == "font_ascii" and rpr.find(qn("w:rFonts")) is not None:
                    changes += remove_attrs(rpr.find(qn("w:rFonts")), *_FONT_ATTRS)
                    drop_if_empty(rpr.find(qn("w:rFonts")))
                else:
                    changes += remove_children(rpr, *_DIRECT_TAGS.get(name, ()))
    return changes


_KEEP_TAGS = {qn("w:pPr"), qn("w:r")}


@fixer("TEXT-08")
def fix_empty_paragraphs(ctx: FixContext) -> int:
    """Delete empty paragraphs used for spacing, keeping the allowed number."""
    from ..rules.text import _is_spacing_paragraph

    keep = int(ctx.expected.get("max_consecutive_empty", 1))
    removed = 0
    for p in ctx.finding_paragraphs():
        run = []
        for q in ctx.view.paragraphs[p.index :]:
            if not _is_spacing_paragraph(q):
                break
            run.append(q)
        for q in run[keep:]:
            el = ctx.element(q.index)
            # Only plain empty paragraphs: never one holding a bookmark or comment mark.
            if el.getparent() is None or any(child.tag not in _KEEP_TAGS for child in el):
                continue
            el.getparent().remove(el)
            removed += 1
    return removed
