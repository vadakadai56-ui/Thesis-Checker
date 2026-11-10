"""Body text rules: font family (TEXT-01) and font size (TEXT-02).

"Body text" = ordinary paragraphs after the first heading, not headings, not in
tables, not captions/TOC/title styles (see DocumentView). Each paragraph with a
problem gives ONE finding, naming what was found, so the list stays readable.
"""

from __future__ import annotations

from ..document_view import SINGLE_LINE, ParagraphView
from ..units import cm_to_twips, fmt_cm, fmt_pt
from .registry import RuleContext, SkipRule, paragraph_location, rule

SIZE_TOLERANCE_PT = 0.25  # Word allows half-point sizes; anything closer counts as equal


@rule(
    "TEXT-01",
    title="Body font",
    how_to_fix=(
        "Home → Styles → right-click 'Normal' → Modify → choose the font. "
        "Then select the text and press Ctrl+Space to clear direct formatting."
    ),
)
def check_body_font(ctx: RuleContext) -> None:
    expected = ctx.cfg.expected["font"]
    body = ctx.body_paragraphs()
    if not body:
        raise SkipRule("No body text found after the first heading.")

    for p in body:
        wrong: set[str] = set()
        for run in p.runs:
            wrong |= {f for f in run.fonts_used() if f.casefold() != expected.casefold()}
        if wrong:
            found = ", ".join(sorted(wrong))
            ctx.report(
                message=f"Body text uses {found}; the required font is {expected}.",
                location=paragraph_location(p),
                expected=expected,
                found=found,
            )


@rule(
    "TEXT-02",
    title="Body font size",
    how_to_fix=(
        "Home → Styles → right-click 'Normal' → Modify → set the size. "
        "Then select the text and press Ctrl+Space to clear direct formatting."
    ),
)
def check_body_size(ctx: RuleContext) -> None:
    expected = float(ctx.cfg.expected["size_pt"])
    body = ctx.body_paragraphs()
    if not body:
        raise SkipRule("No body text found after the first heading.")

    for p in body:
        wrong = {
            run.size_pt
            for run in p.runs
            if run.text.strip() and abs(run.size_pt - expected) > SIZE_TOLERANCE_PT
        }
        if wrong:
            found = ", ".join(fmt_pt(s) for s in sorted(wrong))
            ctx.report(
                message=f"Body text is {found}; the required size is {fmt_pt(expected)}.",
                location=paragraph_location(p),
                expected=fmt_pt(expected),
                found=found,
            )


# --------------------------------------------------------------- paragraph layout
#
# Lists (bullets/numbers) and the reference list have their own layout, so the
# spacing/indent rules below skip them; REF-03 checks the reference list.


def _layout_paragraphs(ctx: RuleContext, *, skip_lists: bool) -> list[ParagraphView]:
    body = [
        p
        for p in ctx.body_paragraphs()
        if not ctx.regions.contains("references", p.index)
        and not (skip_lists and p.numbering is not None)
    ]
    if not body:
        raise SkipRule("No body text found after the first heading.")
    return body


def _line_spacing_text(p: ParagraphView) -> str:
    if p.line_rule == "auto":
        lines = p.line_value / SINGLE_LINE
        return f"{lines:g} line" + ("" if lines == 1 else "s")
    word = "exactly" if p.line_rule == "exact" else "at least"
    return f"{word} {fmt_pt(p.line_value / 20)}"


@rule(
    "TEXT-03",
    title="Line spacing",
    how_to_fix="Home → Styles → right-click 'Normal' → Modify → Format → Paragraph → Line spacing.",
)
def check_line_spacing(ctx: RuleContext) -> None:
    expected = float(ctx.expected["line_spacing"])
    for p in _layout_paragraphs(ctx, skip_lists=False):
        lines = p.line_spacing_lines
        if lines is not None and abs(lines - expected) <= 0.05:
            continue
        ctx.report(
            message=f"Line spacing is {_line_spacing_text(p)}; required {expected:g} lines.",
            location=paragraph_location(p),
            expected=f"{expected:g} lines",
            found=_line_spacing_text(p),
        )


@rule(
    "TEXT-04",
    title="Text alignment",
    how_to_fix=(
        "Select the paragraph and choose the alignment in Home → Paragraph (Ctrl+J = justify)."
    ),
)
def check_alignment(ctx: RuleContext) -> None:
    expected = ctx.expected["alignment"]
    for p in _layout_paragraphs(ctx, skip_lists=True):
        if p.alignment != expected:
            ctx.report(
                message=f"Paragraph is {p.alignment}-aligned; required {expected}.",
                location=paragraph_location(p),
                expected=expected,
                found=p.alignment,
            )


@rule(
    "TEXT-05",
    title="Paragraph spacing",
    how_to_fix=(
        "Home → Styles → right-click the style → Modify → Format → Paragraph → "
        "Spacing Before / After."
    ),
)
def check_paragraph_spacing(ctx: RuleContext) -> None:
    exp_before = float(ctx.expected.get("before_pt", 0))
    exp_after = float(ctx.expected.get("after_pt", 0))
    tolerance = float(ctx.expected.get("tolerance_pt", 0.5))
    for p in _layout_paragraphs(ctx, skip_lists=True):
        before, after = p.space_before / 20, p.space_after / 20  # twips -> pt
        if abs(before - exp_before) <= tolerance and abs(after - exp_after) <= tolerance:
            continue
        ctx.report(
            message=(
                f"Spacing is {fmt_pt(before)} before / {fmt_pt(after)} after; required "
                f"{fmt_pt(exp_before)} / {fmt_pt(exp_after)}."
            ),
            location=paragraph_location(p),
            expected=f"before {fmt_pt(exp_before)}, after {fmt_pt(exp_after)}",
            found=f"before {fmt_pt(before)}, after {fmt_pt(after)}",
        )


@rule(
    "TEXT-06",
    title="First-line indent",
    how_to_fix=(
        "Home → Styles → right-click the body style → Modify → Format → Paragraph → "
        "Special: First line."
    ),
)
def check_first_line_indent(ctx: RuleContext) -> None:
    expected_cm = float(ctx.expected["first_line_cm"])
    tolerance = cm_to_twips(float(ctx.expected.get("tolerance_cm", 0.05)))
    for p in _layout_paragraphs(ctx, skip_lists=True):
        if abs(p.first_line - cm_to_twips(expected_cm)) <= tolerance:
            continue
        found = f"hanging {fmt_cm(-p.first_line)}" if p.first_line < 0 else fmt_cm(p.first_line)
        ctx.report(
            message=f"First-line indent is {found}; required {expected_cm:.2f} cm.",
            location=paragraph_location(p),
            expected=f"{expected_cm:.2f} cm",
            found=found,
        )


# Character properties that count as "direct formatting" for TEXT-07.
_DIRECT_NAMES = {
    "font_ascii": "font",
    "size_pt": "size",
    "bold": "bold",
    "italic": "italic",
    "underline": "underline",
    "color": "colour",
    "caps": "capitals",
    "highlight": "highlight",
}


@rule(
    "TEXT-07",
    title="Direct formatting",
    how_to_fix=(
        "Select the paragraph and press Ctrl+Space to remove direct character "
        "formatting, then use styles instead."
    ),
)
def check_direct_formatting(ctx: RuleContext) -> None:
    max_percent = float(ctx.expected.get("max_percent", 50))
    for p in ctx.body_paragraphs():
        total = sum(len(r.text.strip()) for r in p.runs)
        if not total:
            continue
        overridden = sum(len(r.text.strip()) for r in p.runs if r.direct)
        percent = 100 * overridden / total
        if percent <= max_percent:
            continue
        props = sorted({_DIRECT_NAMES[d] for r in p.runs for d in r.direct})
        ctx.report(
            message=(
                f"{percent:.0f}% of this paragraph has direct formatting "
                f"({', '.join(props)}) instead of using the style."
            ),
            location=paragraph_location(p),
            expected=f"at most {max_percent:g}% direct formatting",
            found=f"{percent:.0f}% ({', '.join(props)})",
        )


def _is_spacing_paragraph(p: ParagraphView) -> bool:
    """An empty paragraph that is only there to make space."""
    return (
        p.is_empty
        and not p.in_table
        and not p.has_image
        and not p.has_math
        and not p.has_page_break
        and not p.ends_section
    )


@rule(
    "TEXT-08",
    title="Empty paragraphs used for spacing",
    how_to_fix="Delete the empty lines and use 'Spacing Before/After' or a page break instead.",
)
def check_empty_paragraphs(ctx: RuleContext) -> None:
    max_run = int(ctx.expected.get("max_consecutive_empty", 1))
    title = ctx.regions.get("title_page")
    start = title.end if title else 0
    run: list[ParagraphView] = []
    for p in [*ctx.view.paragraphs[start:], None]:
        if p is not None and _is_spacing_paragraph(p):
            run.append(p)
            continue
        if len(run) > max_run:
            ctx.report(
                message=f"{len(run)} empty paragraphs in a row are used for spacing.",
                location=paragraph_location(run[0]),
                expected=f"at most {max_run} empty paragraph(s) in a row",
                found=f"{len(run)} in a row",
            )
        run = []
