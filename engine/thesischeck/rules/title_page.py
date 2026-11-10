"""Title page rules: required fields present (TITLE-01) and the current year (TITLE-02).

Each field in the profile's `title_page.fields` has regular-expression `patterns`;
a field counts as present if any pattern matches the title page text.
"""

from __future__ import annotations

import re

from ..model import Location
from .registry import RuleContext, SkipRule, paragraph_location, rule

_PLACEHOLDER_RE = re.compile(r"<[^<>]{2,}>")


def _title_text(ctx: RuleContext) -> tuple[str, Location]:
    paras = ctx.regions.paragraphs("title_page")
    if not paras:
        raise SkipRule("No title page found (no text before the first heading).")
    text = "\n".join(p.clean_text for p in paras)
    return text, paragraph_location(paras[0])


@rule(
    "TITLE-01",
    title="Title page fields",
    how_to_fix="Fill in every field of the title page exactly as the template shows.",
)
def check_title_fields(ctx: RuleContext) -> None:
    text, location = _title_text(ctx)
    for field in ctx.setting("title_page", "fields", default=[]) or []:
        if not isinstance(field, dict) or not field.get("patterns"):
            continue  # a field we can't recognise automatically (e.g. the name)
        if not any(re.search(p, text, re.IGNORECASE | re.MULTILINE) for p in field["patterns"]):
            ctx.report(
                message=f"The title page is missing: {field.get('label', field.get('id'))}.",
                location=location,
                expected=field.get("label", field.get("id")),
                found="not found",
            )
    placeholders = _PLACEHOLDER_RE.findall(text)
    if placeholders:
        ctx.report(
            message="The title page still contains template placeholders.",
            location=location,
            expected="your own details",
            found=", ".join(placeholders[:3]),
        )


@rule(
    "TITLE-02",
    title="Title page year",
    how_to_fix="Put the year of submission on the title page.",
)
def check_title_year(ctx: RuleContext) -> None:
    text, location = _title_text(ctx)
    years = [int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)]
    if not years:
        raise SkipRule("No year found on the title page.")
    if max(years) != ctx.today.year:
        ctx.report(
            message=f"The title page says {max(years)}, but it is {ctx.today.year}.",
            location=location,
            expected=str(ctx.today.year),
            found=str(max(years)),
        )
