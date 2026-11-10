"""Page-number rules: present (PGNUM-01), position + format (PGNUM-02), title page (PGNUM-03).

Page numbers live in headers/footers as a PAGE field. Each Word section has up to
three footers ("first page", "odd/default", "even") and inherits any it doesn't
define from the section before ("Link to previous"); DocumentView resolves that.
"""

from __future__ import annotations

from ..document_view import HeaderFooterView, SectionView
from .registry import RuleContext, SkipRule, part_location, rule, section_location

_FORMAT_NAMES = {
    None: "arabic",
    "decimal": "arabic",
    "lowerRoman": "roman",
    "upperRoman": "roman",
    "lowerLetter": "letters",
    "upperLetter": "letters",
}
_SWITCH_NAMES = {"roman": "roman", "alphabetic": "letters", "arabic": "arabic"}


def _all_parts(section: SectionView) -> list[HeaderFooterView]:
    return [hf for hf in (*section.headers.values(), *section.footers.values()) if hf]


def _has_any_page_number(ctx: RuleContext) -> bool:
    return any(hf.has_page_field for s in ctx.view.sections for hf in _all_parts(s))


def _single_page(ctx: RuleContext, section: SectionView) -> bool:
    pages = {p.page_estimate for p in ctx.view.paragraphs if p.section_index == section.index}
    return len(pages) <= 1


def _is_title_only_section(ctx: RuleContext, section: SectionView) -> bool:
    """A 'different first page' section that holds a single page (the title page)."""
    return section.title_page and _single_page(ctx, section)


@rule(
    "PGNUM-01",
    title="Page numbers present",
    how_to_fix="Insert → Page Number → Bottom of Page → choose the position.",
)
def check_page_numbers_present(ctx: RuleContext) -> None:
    if not _has_any_page_number(ctx):
        ctx.report(
            message="The document has no page numbers.",
            location=part_location("footer"),
            expected="a page-number field",
            found="none",
        )


@rule(
    "PGNUM-02",
    title="Page number position and format",
    how_to_fix=(
        "Double-click the footer, select the page number and align it "
        "(Home → Paragraph); Insert → Page Number → Format Page Numbers for the style."
    ),
)
def check_page_number_position(ctx: RuleContext) -> None:
    if not _has_any_page_number(ctx):
        raise SkipRule("The document has no page numbers (see PGNUM-01).")
    position = ctx.expected.get("position", "bottom_center")
    want_place, want_align = position.split("_")
    want_align = {"centre": "center"}.get(want_align, want_align)
    want_format = ctx.expected.get("format", "arabic")

    for section in ctx.view.sections:
        if _is_title_only_section(ctx, section):
            continue  # its only page is the title page (PGNUM-03)
        expected_part = section.footers if want_place == "bottom" else section.headers
        other_part = section.headers if want_place == "bottom" else section.footers
        here = expected_part.get("default")
        there = other_part.get("default")
        location = section_location(ctx.view, section)
        name = f"Section {section.index + 1}"
        if here and here.has_page_field:
            if here.page_alignment != want_align:
                ctx.report(
                    message=f"{name}: the page number is {here.page_alignment}-aligned.",
                    location=location,
                    expected=position.replace("_", " "),
                    found=f"{want_place} {here.page_alignment}",
                )
        elif there and there.has_page_field:
            ctx.report(
                message=f"{name}: the page number is at the wrong edge of the page.",
                location=location,
                expected=position.replace("_", " "),
                found=("top" if want_place == "bottom" else "bottom") + f" {there.page_alignment}",
            )
            continue
        else:
            ctx.report(
                message=f"{name} has no page numbers.",
                location=location,
                expected=position.replace("_", " "),
                found="no page number",
            )
            continue
        found_format = _SWITCH_NAMES.get(
            (here.page_format_switch or "").lower()
        ) or _FORMAT_NAMES.get(section.page_number_format, section.page_number_format)
        if found_format != want_format:
            ctx.report(
                message=f"{name}: page numbers use {found_format} numerals.",
                location=location,
                expected=want_format,
                found=found_format,
            )


@rule(
    "PGNUM-03",
    title="Title page numbering",
    how_to_fix=(
        "Double-click the footer → tick 'Different First Page'. To start counting "
        "after the title page, put a section break after it and set "
        "Format Page Numbers → Start at 1."
    ),
)
def check_title_page_number(ctx: RuleContext) -> None:
    sections = ctx.view.sections
    if not sections or ctx.regions.get("title_page") is None:
        raise SkipRule("No title page found.")
    first = sections[0]
    kind = "first" if first.title_page else "default"
    shown = any(
        hf is not None and hf.has_page_field
        for hf in (first.footers.get(kind), first.headers.get(kind))
    )
    location = section_location(ctx.view, first)
    if shown and not ctx.expected.get("title_page_shows_number", False):
        ctx.report(
            message="The title page shows a page number.",
            location=location,
            expected="no number on the title page",
            found="page number shown",
        )
    counted_expected = ctx.expected.get("title_page_counted")
    if counted_expected is None:
        return
    restarts = first.page_number_start == 0 or (
        len(sections) > 1 and sections[1].page_number_start == 1 and _single_page(ctx, first)
    )
    counted = not restarts
    if counted != bool(counted_expected):
        ctx.report(
            message=(
                "The title page is counted: the next page is not page 1."
                if counted
                else "Numbering restarts after the title page, but the title page should count."
            ),
            location=location,
            expected="title page counted"
            if counted_expected
            else "first page after the title page is 1",
            found="counted" if counted else "not counted",
        )
