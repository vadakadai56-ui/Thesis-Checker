"""Heading rules: heading styles used (HEAD-01), formatting (HEAD-02), no skipped
levels (HEAD-03), numbering (HEAD-04), capitals (HEAD-05), new page (HEAD-06)."""

from __future__ import annotations

import re
from typing import Any

from ..document_view import ParagraphView
from ..regions import norm
from ..units import fmt_pt
from .registry import RuleContext, SkipRule, paragraph_location, rule


@rule(
    "HEAD-03",
    title="No skipped heading levels",
    how_to_fix=(
        "Change the heading's style (Home → Styles) so levels go 1 → 2 → 3 "
        "without jumping, e.g. use Heading 2 under a Heading 1."
    ),
)
def check_skipped_levels(ctx: RuleContext) -> None:
    headings = ctx.view.headings
    if not headings:
        raise SkipRule("No headings found (Heading 1–3 styles), so levels can't be checked.")

    previous = 0  # "level 0" = before the first heading
    for h in headings:
        level = h.heading_level or 0
        if level > previous + 1:
            if previous == 0:
                message = f"The first heading is level {level}; start with a level-1 heading."
            else:
                message = (
                    f"Heading level jumps from {previous} to {level} "
                    f"(level {previous + 1} is skipped)."
                )
            ctx.report(
                message=message,
                location=paragraph_location(h),
                expected=f"level ≤ {previous + 1}",
                found=f"level {level}",
            )
        previous = level


_END_PUNCTUATION = tuple(".,;:!?…")


@rule(
    "HEAD-01",
    title="Headings use heading styles",
    how_to_fix=(
        "Click in the line and choose the heading style (Home → Styles → Heading 1/2/3 "
        "or your template's Level-heading styles) instead of making body text bold."
    ),
)
def check_fake_headings(ctx: RuleContext) -> None:
    max_words = int(ctx.expected.get("max_words", 12))
    paragraphs = ctx.view.paragraphs
    for p in ctx.body_paragraphs():
        text = p.clean_text
        letters = [r for r in p.runs if r.text.strip()]
        if (
            p.numbering is not None
            or not letters
            or len(text.split()) > max_words
            or text.endswith(_END_PUNCTUATION)
            or not all(r.bold for r in letters)
        ):
            continue
        following = next((q for q in paragraphs[p.index + 1 :] if not q.is_empty), None)
        if following is None or not following.is_body:
            continue  # a heading is followed by ordinary text
        ctx.report(
            message="This looks like a heading typed as bold text; use a heading style.",
            location=paragraph_location(p),
            expected="a heading style",
            found=f"bold '{p.style_name or 'Normal'}' paragraph",
        )


def _font_family(name: str) -> str:
    """'Times New Roman Bold' is Times New Roman in bold; compare families only."""
    return re.sub(r"\s+(bold|italic|regular)$", "", name.strip(), flags=re.IGNORECASE).casefold()


def _heading_props(h: ParagraphView) -> dict[str, Any]:
    runs = [r for r in h.runs if r.text.strip()]
    first = runs[0] if runs else None
    return {
        "font": first.font_ascii if first else None,
        "size_pt": first.size_pt if first else None,
        "bold": all(r.bold or "bold" in r.font_ascii.casefold() for r in runs) if runs else None,
        "caps": all(r.caps for r in runs) if runs else None,
        "align": h.alignment,
        "before_pt": h.space_before / 20,
        "after_pt": h.space_after / 20,
    }


def _differs(key: str, want: Any, got: Any) -> bool:
    if got is None:
        return False
    if key == "font":
        return _font_family(want) != _font_family(got)
    if key == "align":
        return {"centre": "center"}.get(want, want) != got
    if key in ("size_pt", "before_pt", "after_pt"):
        return abs(float(want) - float(got)) > 0.25
    return bool(want) != bool(got)


_PROP_NAMES = {
    "font": "font",
    "size_pt": "size",
    "bold": "bold",
    "caps": "capitals",
    "align": "alignment",
    "before_pt": "space before",
    "after_pt": "space after",
}


def _describe(key: str, value: Any) -> str:
    if key in ("size_pt", "before_pt", "after_pt"):
        return f"{_PROP_NAMES[key]} {fmt_pt(float(value))}"
    if key in ("bold", "caps"):
        return _PROP_NAMES[key] if value else f"not {_PROP_NAMES[key]}"
    return f"{_PROP_NAMES[key]} {value}"


@rule(
    "HEAD-02",
    title="Heading formatting",
    how_to_fix=(
        "Home → Styles → right-click the heading style → Modify; then select the "
        "heading and press Ctrl+Space to remove direct formatting."
    ),
)
def check_heading_format(ctx: RuleContext) -> None:
    by_level = {str(k): v for k, v in ctx.expected.items()}
    headings = [h for h in ctx.view.headings if str(h.heading_level) in by_level]
    if not headings:
        raise SkipRule("No headings found for the levels this profile describes.")
    for h in headings:
        want = by_level[str(h.heading_level)]
        got = _heading_props(h)
        wrong = [k for k, v in want.items() if k in got and _differs(k, v, got[k])]
        if wrong:
            ctx.report(
                message=(
                    f"Level-{h.heading_level} heading formatting differs: "
                    f"{', '.join(_PROP_NAMES[k] for k in wrong)}."
                ),
                location=paragraph_location(h),
                expected=", ".join(_describe(k, want[k]) for k in wrong),
                found=", ".join(_describe(k, got[k]) for k in wrong),
            )


@rule(
    "HEAD-04",
    title="Heading numbering",
    how_to_fix=(
        "Number chapters like the guideline shows (e.g. '1.', '1.1.', '1.1.1.') and "
        "leave Introduction, Conclusions, References etc. unnumbered."
    ),
)
def check_heading_numbering(ctx: RuleContext) -> None:
    formats = list(ctx.expected.get("format", []))
    unnumbered = {norm(t) for t in ctx.expected.get("unnumbered", [])}
    headings = [h for h in ctx.view.headings if not ctx.regions.after_marker("appendixes", h.index)]
    if not headings:
        raise SkipRule("No headings found.")
    for h in headings:
        level = h.heading_level or 1
        is_list = h.heading_number_source == "list"
        if norm(h.text) in unnumbered:
            if h.heading_number:
                ctx.report(
                    message=f"'{h.snippet}' should not be numbered.",
                    location=paragraph_location(h),
                    expected="no number",
                    found=h.heading_number,
                    fixable=is_list,
                )
            continue
        if level > len(formats):
            continue
        want = formats[level - 1]
        want_depth = len(re.findall(r"\d+", want))
        want_dot = want.endswith(".")
        if not h.heading_number:
            message, found = "This heading has no number.", "no number"
        elif len(h.heading_number.split(".")) != want_depth or h.heading_number_dot != want_dot:
            found = h.heading_number + ("." if h.heading_number_dot else "")
            message = f"Heading number '{found}' doesn't match the format '{want}'."
        else:
            continue
        ctx.report(
            message=message,
            location=paragraph_location(h),
            expected=f"format {want}",
            found=found,
            fixable=is_list,
        )


def _is_all_caps(h: ParagraphView) -> bool:
    runs = [r for r in h.runs if any(c.isalpha() for c in r.text)]
    return all(r.caps or r.text == r.text.upper() for r in runs)


@rule(
    "HEAD-05",
    title="Heading capitalisation",
    how_to_fix=(
        "Turn on 'All caps' in the heading style (Modify → Format → Font) rather "
        "than retyping the heading in capitals."
    ),
)
def check_heading_caps(ctx: RuleContext) -> None:
    by_level = {str(k): v for k, v in ctx.expected.items()}
    for h in ctx.view.headings:
        mode = by_level.get(str(h.heading_level), "as_typed")
        title = re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", h.clean_text)
        if mode == "all_caps" and not _is_all_caps(h):
            ok, want = False, "ALL CAPITALS"
        elif mode == "sentence_case":
            letters = [c for c in title if c.isalpha()]
            ok = not letters or (letters[0].isupper() and not _is_all_caps(h))
            want = "Sentence case (first letter capital)"
        else:
            continue
        if not ok:
            ctx.report(
                message=f"Level-{h.heading_level} heading should be in {want}.",
                location=paragraph_location(h),
                expected=want,
                found=h.snippet,
            )


def _starts_new_page(view_paragraphs: tuple[ParagraphView, ...], h: ParagraphView) -> bool:
    if h.page_break_before or h.starts_with_page_break:
        return True
    for prev in reversed(view_paragraphs[: h.index]):
        if prev.has_page_break or (prev.ends_section and prev.section_break_type != "continuous"):
            return True
        if not prev.is_empty:
            return False
    return True  # the very first paragraph of the document


@rule(
    "HEAD-06",
    title="Chapters start on a new page",
    how_to_fix=(
        "Turn on 'Page break before' in the level-1 heading style "
        "(Modify → Format → Paragraph → Line and Page Breaks)."
    ),
)
def check_new_page(ctx: RuleContext) -> None:
    if not ctx.expected.get("new_page", True):
        return
    level1 = [h for h in ctx.view.headings if h.heading_level == 1]
    if not level1:
        raise SkipRule("No level-1 headings found.")
    for h in level1:
        if not _starts_new_page(ctx.view.paragraphs, h):
            ctx.report(
                message="This chapter heading does not start on a new page.",
                location=paragraph_location(h),
                expected="starts on a new page",
                found="continues on the same page",
            )
