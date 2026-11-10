"""Body text rules: font family (TEXT-01) and font size (TEXT-02).

"Body text" = ordinary paragraphs after the first heading, not headings, not in
tables, not captions/TOC/title styles (see DocumentView). Each paragraph with a
problem gives ONE finding, naming what was found, so the list stays readable.
"""

from __future__ import annotations

from ..units import fmt_pt
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
    body = ctx.view.body_paragraphs
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
    body = ctx.view.body_paragraphs
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
