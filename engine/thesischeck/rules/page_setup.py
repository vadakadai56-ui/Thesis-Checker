"""Page setup rules: margins (PAGE-01) and paper size (PAGE-02).

Values in the profile are in cm; Word stores twips. We compare in twips.
"""

from __future__ import annotations

from ..document_view import SectionView
from ..units import PAPER_SIZES_TWIPS, PAPER_TOLERANCE_TWIPS, cm_to_twips, fmt_cm, paper_name
from .registry import RuleContext, rule, section_location, settings_location

SIDES = ("top", "bottom", "left", "right")


def _found_margins(section: SectionView) -> dict[str, int | None]:
    return {
        "top": section.margin_top,
        "bottom": section.margin_bottom,
        "left": section.margin_left,
        "right": section.margin_right,
    }


def _rotations(expected: dict[str, float]) -> list[dict[str, float]]:
    """The expected margins plus both 90° rotations.

    When a page is turned to landscape, its margins usually turn with it (the
    binding edge stays the same physical edge), so for landscape sections we
    accept the margins rotated either way (BUILD_PROMPT §5, PAGE-03 note).
    """
    t, b, left, r = (expected[s] for s in SIDES)
    clockwise = {"top": left, "right": t, "bottom": r, "left": b}
    counter = {"top": r, "left": t, "bottom": left, "right": b}
    return [expected, clockwise, counter]


def _matches(found: dict[str, int | None], expected: dict[str, float], tol: float) -> bool:
    return all(found[s] is not None and abs(found[s] - expected[s]) <= tol for s in SIDES)


@rule(
    "PAGE-01",
    title="Page margins",
    how_to_fix="Layout → Margins → Custom Margins…, enter the values, Apply to: Whole document.",
)
def check_margins(ctx: RuleContext) -> None:
    exp_cfg = ctx.cfg.expected
    expected = {s: cm_to_twips(exp_cfg[f"{s}_cm"]) for s in SIDES}
    tolerance = cm_to_twips(exp_cfg.get("tolerance_cm", 0.05))
    expected_text = ", ".join(f"{s} {exp_cfg[f'{s}_cm']:.2f} cm" for s in SIDES)

    for section in ctx.view.sections:
        found = _found_margins(section)
        candidates = _rotations(expected) if section.is_landscape else [expected]
        if any(_matches(found, c, tolerance) for c in candidates):
            continue

        wrong = [s for s in SIDES if found[s] is None or abs(found[s] - expected[s]) > tolerance]
        found_text = ", ".join(
            f"{s} {fmt_cm(found[s])}" if found[s] is not None else f"{s} not set" for s in SIDES
        )
        ctx.report(
            message=(
                f"Section {section.index + 1}: the {', '.join(wrong)} margin"
                f"{'s are' if len(wrong) > 1 else ' is'} not as required "
                f"(allowed difference ±{exp_cfg.get('tolerance_cm', 0.05):.2f} cm)."
            ),
            location=section_location(ctx.view, section),
            expected=expected_text,
            found=found_text,
        )


def _size_text(section: SectionView) -> str:
    if section.page_width is None or section.page_height is None:
        return "not set"
    name = paper_name(section.page_width, section.page_height)
    size = f"{fmt_cm(section.page_width)} × {fmt_cm(section.page_height)}"
    return f"{size} ({name})" if name else size


@rule("PAGE-02", title="Paper size", how_to_fix="Layout → Size → choose the required paper size.")
def check_paper_size(ctx: RuleContext) -> None:
    paper = ctx.cfg.expected["paper"]
    exp_short, exp_long = sorted(PAPER_SIZES_TWIPS[paper])

    for section in ctx.view.sections:
        if section.page_width is not None and section.page_height is not None:
            short, long_ = sorted((section.page_width, section.page_height))
            # Sorting makes the comparison work for portrait and landscape pages.
            if (
                abs(short - exp_short) <= PAPER_TOLERANCE_TWIPS
                and abs(long_ - exp_long) <= PAPER_TOLERANCE_TWIPS
            ):
                continue
        ctx.report(
            message=f"Section {section.index + 1}: the paper size is not {paper}.",
            location=section_location(ctx.view, section),
            expected=paper,
            found=_size_text(section),
        )


@rule(
    "PAGE-03",
    title="Page orientation",
    how_to_fix=(
        "Put the wide content in its own section (Layout → Breaks → Next Page) and "
        "turn only that section to Landscape, or keep the page Portrait."
    ),
)
def check_orientation(ctx: RuleContext) -> None:
    allowed = ctx.expected.get("landscape", "never")  # never | appendices_only | allowed
    if allowed == "allowed":
        return
    for section in ctx.view.sections:
        if not section.is_landscape:
            continue
        first = ctx.view.first_paragraph_of_section(section.index)
        in_appendices = first is not None and ctx.regions.after_marker("appendixes", first.index)
        if allowed == "appendices_only" and in_appendices:
            continue
        where = "outside the appendices" if allowed == "appendices_only" else ""
        ctx.report(
            message=f"Section {section.index + 1} is landscape {where}".rstrip() + ".",
            location=section_location(ctx.view, section),
            expected="portrait" + (" (landscape only in appendices)" if where else ""),
            found="landscape",
        )


@rule(
    "PAGE-04",
    title="Gutter and mirror margins",
    how_to_fix=(
        "Layout → Margins → Custom Margins…: set Gutter to 0 and Multiple pages to Normal."
    ),
)
def check_gutter(ctx: RuleContext) -> None:
    max_gutter = cm_to_twips(ctx.expected.get("gutter_cm", 0)) + cm_to_twips(0.05)
    for section in ctx.view.sections:
        if (section.gutter or 0) > max_gutter:
            ctx.report(
                message=f"Section {section.index + 1} has a gutter (extra binding margin).",
                location=section_location(ctx.view, section),
                expected=f"gutter {ctx.expected.get('gutter_cm', 0):.2f} cm",
                found=f"gutter {fmt_cm(section.gutter or 0)}",
            )
    want_mirror = bool(ctx.expected.get("mirror_margins", False))
    if ctx.view.mirror_margins != want_mirror:
        ctx.report(
            message=(
                "Mirror margins are switched on."
                if ctx.view.mirror_margins
                else "Mirror margins are required but switched off."
            ),
            location=settings_location(),
            expected="mirror margins on" if want_mirror else "mirror margins off",
            found="on" if ctx.view.mirror_margins else "off",
        )
