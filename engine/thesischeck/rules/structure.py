"""Structure rules: required parts present (STRUCT-01) and in order (STRUCT-02),
abstract length and key words (STRUCT-03), length of parts (STRUCT-04).

The parts and how to recognise them come from the profile's `structure` section;
see regions.py. "title_page" and "chapters" are built in.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import Location
from ..regions import Region, phrases
from .registry import RuleContext, SkipRule, paragraph_location, rule

BUILT_IN = {"title_page": "Title page", "chapters": "Numbered chapters"}


def _label(ctx: RuleContext, name: str) -> str:
    if name in BUILT_IN:
        return BUILT_IN[name]
    cfg = ctx.setting("structure", "sections", name, default={}) or {}
    return cfg.get("label") or (phrases(cfg.get("headings")) or [name])[0]


def _order(ctx: RuleContext) -> list[str]:
    """Required parts in order, with optional parts inserted after the part they follow."""
    order = list(ctx.setting("structure", "required_order", default=[]) or [])
    for item in ctx.setting("structure", "optional", default=[]) or []:
        if isinstance(item, dict) and item.get("after") in order:
            order.insert(order.index(item["after"]) + 1, item["name"])
    return order


def _where(ctx: RuleContext, name: str) -> Location:
    index = ctx.regions.position(name)
    if index is None:
        return Location(part="body")
    return paragraph_location(ctx.view.paragraphs[index])


@rule(
    "STRUCT-01",
    title="Required parts present",
    how_to_fix="Add the missing part with its heading, in the place the template shows.",
)
def check_required_parts(ctx: RuleContext) -> None:
    required = ctx.setting("structure", "required_order", default=None)
    if not required:
        raise SkipRule("The profile lists no required parts.")
    for name in required:
        if ctx.regions.position(name) is None:
            ctx.report(
                message=f"Required part missing: {_label(ctx, name)}.",
                location=Location(part="body"),
                expected=_label(ctx, name),
                found="not found",
            )


@rule(
    "STRUCT-02",
    title="Parts in the right order",
    how_to_fix="Move the part (with its heading and text) to its place in the required order.",
)
def check_part_order(ctx: RuleContext) -> None:
    order = _order(ctx)
    found = [(name, ctx.regions.position(name)) for name in order]
    found = [(n, pos) for n, pos in found if pos is not None]
    if len(found) < 2:
        raise SkipRule("Not enough recognised parts to check their order.")
    latest_name, latest_pos = found[0]
    for name, pos in found[1:]:
        if pos < latest_pos:
            ctx.report(
                message=f"{_label(ctx, name)} comes before {_label(ctx, latest_name)}.",
                location=_where(ctx, name),
                expected=" → ".join(_label(ctx, n) for n, _ in found),
                found=f"{_label(ctx, name)} before {_label(ctx, latest_name)}",
            )
        else:
            latest_name, latest_pos = name, pos


def _pages_text(pages: float, rendered: bool) -> str:
    return f"{pages:.0f} page(s)" if rendered else f"about {pages:.1f} page(s)"


def _too_long(pages: float, limit: float, rendered: bool) -> bool:
    # Without Word's saved page breaks the page count is a word-count estimate,
    # so allow a quarter page of slack before reporting.
    return pages > limit + (0 if rendered else 0.25)


def _too_short(pages: float, limit: float, rendered: bool) -> bool:
    return pages < limit - (0 if rendered else 0.25)


def _keyword_line(ctx: RuleContext, region: Region) -> tuple[Any, list[str]] | None:
    labels = [lbl.casefold() for lbl in phrases(ctx.setting("structure", "keyword_labels"))]
    if not labels:
        return None
    for p in ctx.regions.paragraphs(region):
        text = p.clean_text
        if any(text.casefold().startswith(lbl) for lbl in labels):
            after = text.split(":", 1)[1] if ":" in text else ""
            words = [w.strip(" .") for w in re.split(r"[,;]", after) if w.strip(" .")]
            return p, words
    return None


@rule(
    "STRUCT-03",
    title="Abstract length and key words",
    how_to_fix=(
        "Shorten the abstract yourself (ThesisCheck never rewrites text) and give the "
        "required number of key words."
    ),
)
def check_abstracts(ctx: RuleContext) -> None:
    names = ctx.expected.get("sections") or ["abstract"]
    regions = [(n, ctx.regions.get(n)) for n in names]
    regions = [(n, r) for n, r in regions if r is not None]
    if not regions:
        raise SkipRule("No abstract found (see STRUCT-01).")
    rendered = ctx.view.has_rendered_breaks
    for name, region in regions:
        heading = ctx.view.paragraphs[region.marker]
        label = _label(ctx, name)
        max_pages = ctx.expected.get("max_pages")
        pages = ctx.regions.pages(region)
        if max_pages is not None and _too_long(pages, max_pages, rendered):
            ctx.report(
                message=f"{label} is {_pages_text(pages, rendered)} long.",
                location=paragraph_location(heading),
                expected=f"at most {max_pages} page(s)",
                found=_pages_text(pages, rendered),
            )
        max_words = ctx.expected.get("max_words")
        words = ctx.regions.words(region)
        if max_words is not None and words > max_words:
            ctx.report(
                message=f"{label} has {words} words.",
                location=paragraph_location(heading),
                expected=f"at most {max_words} words",
                found=f"{words} words",
            )
        k_min, k_max = ctx.expected.get("keywords_min"), ctx.expected.get("keywords_max")
        if k_min is None and k_max is None:
            continue
        line = _keyword_line(ctx, region)
        if line is None:
            if phrases(ctx.setting("structure", "keyword_labels")):
                ctx.report(
                    message=f"{label}: no key words line found.",
                    location=paragraph_location(heading),
                    expected=f"{k_min}–{k_max} key words",
                    found="no key words line",
                )
            continue
        para, keywords = line
        if (k_min and len(keywords) < k_min) or (k_max and len(keywords) > k_max):
            ctx.report(
                message=f"{label} has {len(keywords)} key words.",
                location=paragraph_location(para),
                expected=f"{k_min}–{k_max} key words",
                found=f"{len(keywords)} key words",
            )


@rule(
    "STRUCT-04",
    title="Length of parts",
    how_to_fix="Adjust the length of the part yourself; ThesisCheck never changes text.",
)
def check_lengths(ctx: RuleContext) -> None:
    rendered = ctx.view.has_rendered_breaks
    checked = False
    for name, limits in (ctx.expected.get("sections") or {}).items():
        region = ctx.regions.get(name)
        if region is None:
            continue
        checked = True
        _check_limits(ctx, _label(ctx, name), region, limits, rendered)
    main = ctx.expected.get("main_text")
    intro, refs = ctx.regions.get("introduction"), ctx.regions.get("references")
    if main and intro and refs and intro.marker is not None and refs.marker is not None:
        checked = True
        region = Region("main_text", intro.marker, intro.marker, refs.marker)
        _check_limits(ctx, "The main text (Introduction to References)", region, main, rendered)
    if not checked:
        raise SkipRule("None of the parts with length limits were found.")


def _check_limits(
    ctx: RuleContext, label: str, region: Region, limits: dict, rendered: bool
) -> None:
    location = paragraph_location(ctx.view.paragraphs[region.marker or region.start])
    pages = ctx.regions.pages(region)
    words = ctx.regions.words(region)
    problems = []
    if limits.get("max_pages") is not None and _too_long(pages, limits["max_pages"], rendered):
        problems.append((f"at most {limits['max_pages']} page(s)", _pages_text(pages, rendered)))
    if limits.get("min_pages") is not None and _too_short(pages, limits["min_pages"], rendered):
        problems.append((f"at least {limits['min_pages']} page(s)", _pages_text(pages, rendered)))
    if limits.get("max_words") is not None and words > limits["max_words"]:
        problems.append((f"at most {limits['max_words']} words", f"{words} words"))
    if limits.get("min_words") is not None and words < limits["min_words"]:
        problems.append((f"at least {limits['min_words']} words", f"{words} words"))
    for expected, found in problems:
        ctx.report(
            message=f"{label} is {found} long; required {expected}.",
            location=location,
            expected=expected,
            found=found,
        )
