"""AI disclosure rules (RTU AI slides): STRUCT-05 and REF-AI-01.

ThesisCheck does NOT detect AI-generated text. These rules only check that, IF a
student used AI tools, the required disclosure and references are written in
the form the university asks for.
"""

from __future__ import annotations

import re
from functools import cache
from importlib import resources

from ..regions import phrases
from ..text_tools import URL_RE, author_date_citations
from .citations import citation_sources, reference_entries
from .registry import RuleContext, SkipRule, paragraph_location, rule

_ACCESS_BRACKET_RE = re.compile(
    r"\[\s*(accessed|skatīts|viewed)\s*\d{1,2}\.\s?\d{1,2}\.\s?\d{4}\.?\s*\]", re.IGNORECASE
)


@cache
def ai_tools() -> dict[str, list[str]]:
    """{developer: [tools]} from data/ai_tools.txt."""
    text = resources.files("thesischeck").joinpath("data/ai_tools.txt").read_text("utf-8")
    tools: dict[str, list[str]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        developer, names = line.split(":", 1)
        tools[developer.strip()] = [n.strip() for n in names.split(",") if n.strip()]
    return tools


def _word_in(word: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.IGNORECASE) is not None


def ai_reference(text: str) -> str | None:
    """The developer if this reference-list entry is an AI-tool reference, else None."""
    for developer, tools in ai_tools().items():
        if any(_word_in(t, text) for t in tools) and (
            _word_in(developer, text) or "prompt" in text.casefold()
        ):
            return developer
    return None


@rule(
    "STRUCT-05",
    title="AI tools named in the Introduction",
    how_to_fix=(
        "If you used AI tools (also for grammar or translation), add a paragraph "
        "'Tools used in writing this thesis' to the Introduction naming each tool and "
        "what you used it for."
    ),
)
def check_ai_tools_paragraph(ctx: RuleContext) -> None:
    intro = ctx.regions.get("introduction")
    if intro is None:
        raise SkipRule("No Introduction found.")
    wanted = [
        phrase.casefold()
        for values in (ctx.setting("ai_disclosure", "heading_phrases", default={}) or {}).values()
        for phrase in phrases(values)
    ]
    if not wanted:
        raise SkipRule("The profile gives no wording for the AI tools paragraph.")
    text = " ".join(p.clean_text.casefold() for p in ctx.regions.paragraphs(intro))
    if not any(phrase in text for phrase in wanted):
        ctx.report(
            message=(
                "No 'Tools used in writing this thesis' paragraph in the Introduction. "
                "It is required only if you used AI tools."
            ),
            location=paragraph_location(ctx.view.paragraphs[intro.marker]),
            expected="a paragraph naming the tools used",
            found="not found",
        )


@rule(
    "REF-AI-01",
    title="AI tool references",
    how_to_fix=(
        "Write it as: Developer. Tool version. Prompt: <your prompt>. <link to the "
        "chat>. [accessed DD.MM.YYYY.] and cite it in the text as (Developer, YYYY)."
    ),
)
def check_ai_references(ctx: RuleContext) -> None:
    entries = reference_entries(ctx)
    if not entries:
        raise SkipRule("No reference list found.")
    cited = {c.key for _, text in citation_sources(ctx) for c in author_date_citations(text)}
    for entry in entries:
        developer = ai_reference(entry.text)
        if developer is None:
            continue
        missing = []
        if not entry.text.casefold().startswith(developer.casefold()):
            missing.append(f"starts with the developer ({developer})")
        if not re.search(r"\bprompt\s*:", entry.text, re.IGNORECASE):
            missing.append("'Prompt: …'")
        if not URL_RE.search(entry.text):
            missing.append("web address")
        if not _ACCESS_BRACKET_RE.search(entry.text):
            missing.append("[accessed DD.MM.YYYY.]")
        if entry.key not in cited:
            missing.append(f"in-text citation ({developer}, YYYY)")
        if missing:
            ctx.report(
                message=f"AI-tool reference is incomplete: missing {', '.join(missing)}.",
                location=paragraph_location(ctx.view.paragraphs[entry.index]),
                expected="Developer. Tool [version]. Prompt: …. URL. [accessed DD.MM.YYYY.]",
                found=entry.text[:120],
            )
