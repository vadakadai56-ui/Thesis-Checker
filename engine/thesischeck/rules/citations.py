"""Citation and reference-list rules: CITE-01..05 and REF-01..04.

In-text citations are found with patterns (text_tools.py); reference entries are
the paragraphs under the References heading (regions.py). Matching uses the first
author's surname + year, ignoring accents and capitals.
"""

from __future__ import annotations

import itertools
import re

from ..document_view import ParagraphView
from ..model import Location
from ..regions import norm, phrases
from ..text_tools import (
    ACCESS_DATE_RE,
    Citation,
    RefEntry,
    author_date_citations,
    has_any_citation,
    numeric_citations,
    parse_entry,
    quotations,
    sentences,
    sort_key,
)
from ..units import cm_to_twips, fmt_cm, fmt_pt
from .registry import RuleContext, SkipRule, paragraph_location, rule


def reference_entries(ctx: RuleContext) -> list[RefEntry]:
    return [
        parse_entry(p.index, p.text)
        for p in ctx.regions.paragraphs("references")
        if p.heading_level is None
    ]


def citation_sources(ctx: RuleContext) -> list[tuple[ParagraphView | None, str]]:
    """Every piece of text that may contain citations: body, lists, footnotes, text boxes."""
    sources: list[tuple[ParagraphView | None, str]] = []
    for p in ctx.view.paragraphs:
        if p.is_empty or p.heading_level is not None or p.is_caption_like:
            continue
        if ctx.regions.contains("references", p.index) or ctx.regions.contains(
            "title_page", p.index
        ):
            continue
        if any(re.match(r"^\s*TOC\b", i, re.I) for _, i in p.fields):
            continue
        sources.append((p, p.text))
    sources += [(None, text) for text in ctx.view.footnotes]
    sources += [(ctx.view.paragraphs[i], text) for i, text in ctx.view.textboxes]
    return sources


def _location(p: ParagraphView | None) -> Location:
    return paragraph_location(p) if p is not None else Location(part="footnotes")


def _style(ctx: RuleContext) -> str:
    return ctx.profile.extra.get("citation_style", "author-date")


def _matches(citation: Citation, entry: RefEntry) -> bool:
    return (
        entry.year == citation.year
        and bool(entry.key)
        and (
            entry.key == citation.key
            or entry.key.startswith(citation.key)
            or citation.key.startswith(entry.key)
        )
    )


def _require_entries(ctx: RuleContext) -> list[RefEntry]:
    entries = reference_entries(ctx)
    if not entries:
        raise SkipRule("No reference list found.")
    return entries


@rule(
    "CITE-01",
    title="Every citation has a reference",
    how_to_fix="Add the missing source to the reference list, or correct the citation.",
)
def check_citations_have_entries(ctx: RuleContext) -> None:
    entries = _require_entries(ctx)
    reported: set[str] = set()
    for p, text in citation_sources(ctx):
        if _style(ctx) == "numeric":
            for n in numeric_citations(text):
                if not 1 <= n <= len(entries) and str(n) not in reported:
                    reported.add(str(n))
                    ctx.report(
                        message=f"Citation [{n}] has no entry in the reference list.",
                        location=_location(p),
                        expected=f"a number from 1 to {len(entries)}",
                        found=f"[{n}]",
                    )
            continue
        for c in author_date_citations(text):
            if c.text in reported or any(_matches(c, e) for e in entries):
                continue
            reported.add(c.text)
            ctx.report(
                message=f"Citation ({c.text}) has no matching entry in the reference list.",
                location=_location(p),
                expected="a reference entry with the same author and year",
                found=f"({c.text})",
            )


@rule(
    "CITE-02",
    title="Every reference is cited",
    how_to_fix="Cite the source in the text where you use it, or remove it from the list.",
)
def check_entries_are_cited(ctx: RuleContext) -> None:
    entries = _require_entries(ctx)
    texts = [text for _, text in citation_sources(ctx)]
    if _style(ctx) == "numeric":
        cited_numbers = {n for t in texts for n in numeric_citations(t)}
        uncited = [e for i, e in enumerate(entries, 1) if i not in cited_numbers]
    else:
        citations = [c for t in texts for c in author_date_citations(t)]
        uncited = [e for e in entries if not any(_matches(c, e) for c in citations)]
    for entry in uncited:
        ctx.report(
            message="This reference is never cited in the text.",
            location=paragraph_location(ctx.view.paragraphs[entry.index]),
            expected="at least one in-text citation",
            found="not cited",
        )


@rule(
    "CITE-03",
    title="Citation format",
    how_to_fix=(
        "Write citations like (Author, 2026) — surname, comma, year — or as the profile shows."
    ),
)
def check_citation_format(ctx: RuleContext) -> None:
    style = _style(ctx)
    for p, text in citation_sources(ctx):
        if style == "numeric":
            wrong = [f"({c.text})" for c in author_date_citations(text)]
            want = "numbered citations like [1]"
        else:
            wrong = [f"[{n}]" for n in re.findall(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]", text)]
            wrong += [f"({c.text})" for c in author_date_citations(text) if not c.strict]
            want = "(Author, 2026)"
        if wrong:
            ctx.report(
                message=f"Citation not in the required form: {', '.join(wrong[:3])}.",
                location=_location(p),
                expected=want,
                found=", ".join(wrong[:3]),
            )


def _sentence_at(text: str, sents: list[str], offset: int) -> int:
    """Index of the sentence that contains character `offset` of `text`."""
    pos = 0
    for k, sentence in enumerate(sents):
        pos = text.find(sentence, pos) + len(sentence)
        if pos >= offset:
            return k
    return max(len(sents) - 1, 0)


@rule(
    "CITE-04",
    title="Quotation without a reference",
    how_to_fix=(
        'Put the reference right after the quotation, e.g. „…" (Author, 2026, p. 5). '
        "Directly translated text needs a reference too."
    ),
)
def check_quotes_cited(ctx: RuleContext) -> None:
    min_words = int(ctx.expected.get("min_words", 8))
    for p in ctx.body_paragraphs():
        if p.has_math:
            continue
        text = p.clean_text
        sents = sentences(text)
        for _, end, quoted in quotations(text):
            if len(quoted.split()) < min_words:
                continue
            # Check the sentence the quotation ends in, and the next one.
            k = _sentence_at(text, sents, end)
            window = " ".join(sents[k : k + 2])
            if has_any_citation(window) or p.has_note_ref:
                continue
            short = quoted if len(quoted) <= 50 else quoted[:47] + "…"
            ctx.report(
                message="A quotation has no reference in the same or the next sentence.",
                location=paragraph_location(p),
                expected="a reference next to the quotation",
                found=f'„{short}"',
            )


@rule(
    "CITE-05",
    title="Long literature-review paragraph without references",
    how_to_fix="Add references where each source is used, not only at the end of a paragraph.",
)
def check_review_paragraphs(ctx: RuleContext) -> None:
    wanted = [norm(t) for t in phrases(ctx.setting("structure", "literature_review_headings"))]
    if not wanted:
        raise SkipRule("The profile marks no literature-review chapters.")
    chapters = [
        h
        for h in ctx.view.headings
        if h.heading_level == 1 and any(w in norm(h.text) for w in wanted)
    ]
    if not chapters:
        raise SkipRule("No literature-review chapter found.")
    min_words = int(ctx.expected.get("min_words", 120))
    for chapter in chapters:
        region = ctx.regions.chapter_region(chapter.index)
        for p in ctx.view.paragraphs[region.start : region.end]:
            if not p.is_body or len(p.text.split()) <= min_words:
                continue
            if not has_any_citation(p.text) and not p.has_note_ref:
                ctx.report(
                    message=(
                        f"A {len(p.text.split())}-word literature-review paragraph "
                        "has no reference."
                    ),
                    location=paragraph_location(p),
                    expected="references where sources are used",
                    found="no reference",
                )


# ------------------------------------------------------------------ reference list


@rule(
    "REF-01",
    title="Reference entry complete",
    how_to_fix=(
        "Give author, year and title; for online sources also the web address and access date."
    ),
)
def check_entry_complete(ctx: RuleContext) -> None:
    from .ai_disclosure import ai_reference  # AI-tool entries are checked by REF-AI-01

    need_access = ctx.expected.get("access_date_required", True)
    doi_exempt = ctx.expected.get("doi_exempt", True)
    for entry in _require_entries(ctx):
        if ai_reference(entry.text):
            continue
        missing = []
        if entry.year is None:
            missing.append("year")
        parts = [s for s in re.split(r"\.\s+", entry.text) if re.search(r"[^\W\d_]{2}", s)]
        if not entry.key or len(parts) < 2:
            missing.append("author and title")
        online = [u for u in entry.urls if not (doi_exempt and "doi.org" in u.casefold())]
        if online and need_access and not ACCESS_DATE_RE.search(entry.text):
            missing.append("access date")
        if missing:
            ctx.report(
                message=f"Reference entry is missing: {', '.join(missing)}.",
                location=paragraph_location(ctx.view.paragraphs[entry.index]),
                expected="author, year, title"
                + (" (+ URL and access date online)" if online else ""),
                found=entry.text[:120],
            )


@rule(
    "REF-02",
    title="Reference list order",
    how_to_fix="Sort the reference list alphabetically by the first author's surname.",
)
def check_entry_order(ctx: RuleContext) -> None:
    if ctx.expected.get("order", "alphabetical") != "alphabetical":
        raise SkipRule("Only alphabetical order is checked.")
    entries = _require_entries(ctx)
    for previous, entry in itertools.pairwise(entries):
        if sort_key(entry.text) < sort_key(previous.text):
            ctx.report(
                message="This reference is out of alphabetical order.",
                location=paragraph_location(ctx.view.paragraphs[entry.index]),
                expected="alphabetical order",
                found=f"“{entry.text[:40]}” after “{previous.text[:40]}”",
            )


@rule(
    "REF-03",
    title="Reference list formatting",
    how_to_fix=(
        "Select the reference list → Home → Paragraph: Special 'Hanging' with the "
        "required size; set line spacing and spacing before/after."
    ),
)
def check_entry_format(ctx: RuleContext) -> None:
    entries = _require_entries(ctx)
    exp = ctx.expected
    for entry in entries:
        p = ctx.view.paragraphs[entry.index]
        wrong: list[tuple[str, str]] = []
        if "hanging_indent_cm" in exp:
            hanging = -p.first_line if p.first_line < 0 else 0
            if abs(hanging - cm_to_twips(exp["hanging_indent_cm"])) > cm_to_twips(0.05):
                wrong.append(
                    (
                        f"hanging indent {exp['hanging_indent_cm']:.2f} cm",
                        f"hanging {fmt_cm(hanging)}",
                    )
                )
        if "line_spacing" in exp:
            lines = p.line_spacing_lines
            if lines is None or abs(lines - exp["line_spacing"]) > 0.05:
                wrong.append((f"line spacing {exp['line_spacing']:g}", "different line spacing"))
        for key, attr in (("before_pt", "space_before"), ("after_pt", "space_after")):
            if key in exp and abs(getattr(p, attr) / 20 - exp[key]) > 0.5:
                wrong.append(
                    (
                        f"{key[:-3]} {fmt_pt(exp[key])}",
                        f"{key[:-3]} {fmt_pt(getattr(p, attr) / 20)}",
                    )
                )
        if wrong:
            ctx.report(
                message="Reference entry formatting differs: "
                + ", ".join(w[1] for w in wrong)
                + ".",
                location=paragraph_location(p),
                expected=", ".join(w[0] for w in wrong),
                found=", ".join(w[1] for w in wrong),
            )


_SECONDARY_RE = re.compile(
    r"wikipedia|encyclop|enciklop|lecture|slides|lekcij|prezentācij",
    re.IGNORECASE,
)


@rule(
    "REF-04",
    title="Secondary sources",
    how_to_fix="Also cite a primary source (the original article, book or standard).",
)
def check_secondary_sources(ctx: RuleContext) -> None:
    for entry in _require_entries(ctx):
        match = _SECONDARY_RE.search(entry.text)
        if match:
            ctx.report(
                message=f"'{match.group(0)}' is a secondary source — also cite a primary source.",
                location=paragraph_location(ctx.view.paragraphs[entry.index]),
                expected="a primary source as well",
                found=entry.text[:120],
            )
