"""Heading rules. Stage 1: HEAD-03 (no skipped heading levels)."""

from __future__ import annotations

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
