"""Consistency rules: UK/US spelling (CONS-01), abbreviations (CONS-02),
one term written several ways (CONS-03).
"""

from __future__ import annotations

import re
from collections import defaultdict
from functools import cache
from importlib import resources

from ..document_view import ParagraphView
from ..regions import phrases
from ..text_tools import _PAREN_RE, URL_RE
from .registry import RuleContext, SkipRule, paragraph_location, rule


def _prose(ctx: RuleContext) -> list[ParagraphView]:
    """Running text: body paragraphs and lists, outside the reference list."""
    return [
        p
        for p in ctx.view.paragraphs
        if (p.is_body or (p.numbering is not None and not p.in_table and p.heading_level is None))
        and not ctx.regions.contains("references", p.index)
    ]


# ------------------------------------------------------------------- CONS-01


@cache
def spelling_pairs() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """({uk: (us, group)}, {us: (uk, group)}) from data/uk_us_pairs.tsv."""
    text = resources.files("thesischeck").joinpath("data/uk_us_pairs.tsv").read_text("utf-8")
    uk_map: dict[str, tuple[str, str]] = {}
    us_map: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        uk, us, group = line.split("\t")
        uk_map[uk] = (us, group)
        us_map[us] = (uk, group)
    return uk_map, us_map


@rule(
    "CONS-01",
    title="Mixed UK/US spelling",
    how_to_fix=(
        "Pick one spelling (UK or US) and use it everywhere; set the language in "
        "Review → Language so Word's spell-check helps."
    ),
)
def check_spelling_variety(ctx: RuleContext) -> None:
    english = [p for p in _prose(ctx) if p.lang == "en"]
    if not english:
        raise SkipRule("No English text found.")
    uk_map, us_map = spelling_pairs()
    # group -> variant ("uk"/"us") -> list of (word, paragraph)
    seen: dict[str, dict[str, list[tuple[str, ParagraphView]]]] = defaultdict(
        lambda: {"uk": [], "us": []}
    )
    for p in english:
        for word in re.findall(r"[A-Za-z]+", p.text):
            low = word.lower()
            if low in uk_map:
                seen[uk_map[low][1]]["uk"].append((low, p))
            elif low in us_map:
                seen[us_map[low][1]]["us"].append((low, p))
    for variants in seen.values():
        uk, us = variants["uk"], variants["us"]
        if not uk or not us:
            continue
        # The minority is the odd one out; on a tie, whichever appeared second.
        if len(uk) != len(us):
            minority, majority = ("uk", "us") if len(uk) < len(us) else ("us", "uk")
        else:
            later_uk = uk[0][1].index > us[0][1].index
            minority, majority = ("uk", "us") if later_uk else ("us", "uk")
        name = {"uk": "UK", "us": "US"}
        reported: set[str] = set()
        for word, p in variants[minority]:
            if word in reported:
                continue
            reported.add(word)
            other = (uk_map if minority == "uk" else us_map)[word][0]
            ctx.report(
                message=(
                    f"'{word}' is {name[minority]} spelling, but the text mostly uses "
                    f"{name[majority]} spelling ('{other}')."
                ),
                location=paragraph_location(p),
                expected=f"{name[majority]} spelling: {other}",
                found=word,
            )


# ------------------------------------------------------------------- CONS-02

_ABBR_RE = re.compile(r"(?<![\w\-/])([A-ZĀČĒĢĪĶĻŅŠŪŽ][A-ZĀČĒĢĪĶĻŅŠŪŽ0-9]{1,5})s?(?![\w\-/])")
_ROMAN_RE = re.compile(r"^[IVXLCDM]+$")


def _strip_citations_and_urls(text: str) -> str:
    text = URL_RE.sub(" ", text)
    return _PAREN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _is_upper_word(word: str) -> bool:
    letters = [c for c in word if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


@rule(
    "CONS-02",
    title="Abbreviation used before it is defined",
    how_to_fix=(
        "Write the full term the first time, followed by the abbreviation in "
        "brackets — e.g. 'continuous integration (CI)' — or add it to the list of "
        "abbreviations."
    ),
)
def check_abbreviations(ctx: RuleContext) -> None:
    allowed = {a.upper() for a in ctx.expected.get("allow", []) or []}
    defined: set[str] = set()
    for p in ctx.regions.paragraphs("abbreviations"):
        first = p.clean_text.split(" ", 1)[0].strip(" –-:,")
        if first:
            defined.add(first)
    reported: set[str] = set()
    for p in _prose(ctx):
        text = _strip_citations_and_urls(p.clean_text)
        words = text.split()
        if words and sum(_is_upper_word(w) for w in words) / len(words) > 0.5:
            continue  # a line typed in capitals, not abbreviations
        for match in _ABBR_RE.finditer(text):
            abbr = match.group(1)
            if sum(c.isalpha() for c in abbr) < 2 or _ROMAN_RE.match(abbr):
                continue
            if abbr in allowed or abbr in defined or abbr in reported:
                continue
            before = text[: match.start()].rstrip()
            after = text[match.end() :].lstrip()
            neighbours = (before.split()[-1:] or [""])[0], (after.split()[:1] or [""])[0]
            if any(_is_upper_word(n.strip(".,;:()")) for n in neighbours):
                continue  # part of a phrase in capitals
            if before.endswith("(") or after.startswith("("):
                defined.add(abbr)  # "Long form (ABBR)" or "ABBR (long form)"
                continue
            reported.add(abbr)
            ctx.report(
                message=f"'{abbr}' is used before it is defined.",
                location=paragraph_location(p),
                expected=f"defined at first use, e.g. 'full term ({abbr})'",
                found=abbr,
            )


# ------------------------------------------------------------------- CONS-03

_STOPWORDS = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "can",
        "may",
        "might",
        "must",
        "will",
        "would",
        "shall",
        "should",
        "could",
        "do",
        "does",
        "did",
        "not",
        "no",
        "any",
        "some",
        "every",
        "each",
        "all",
        "one",
        "ones",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "into",
        "onto",
        "up",
        "down",
        "out",
        "over",
        "un",
        "ar",
        "par",
        "uz",
        "no",
        "ir",
        "kā",
        "ka",
        "vai",
        "bet",
        "arī",
        "to",
        "tas",
        "tā",
        "šo",
        "šis",
    ]
)


@rule(
    "CONS-03",
    title="Same term written different ways",
    how_to_fix="Choose one form (e.g. 'email' or 'e-mail') and use it everywhere.",
)
def check_term_variants(ctx: RuleContext) -> None:
    paragraphs = _prose(ctx)
    if not paragraphs:
        raise SkipRule("No body text found.")
    tokenised = [(p, re.findall(r"[A-Za-zĀ-ž]+(?:-[A-Za-zĀ-ž]+)*", p.text)) for p in paragraphs]
    closed = {t.lower() for _, tokens in tokenised for t in tokens if "-" not in t and len(t) >= 4}
    hyphen_keys = {
        t.lower().replace("-", "") for _, tokens in tokenised for t in tokens if t.count("-") == 1
    }
    forms: dict[str, dict[str, list[ParagraphView]]] = defaultdict(lambda: defaultdict(list))
    for p, tokens in tokenised:
        for i, token in enumerate(tokens):
            low = token.lower()
            if low.count("-") == 1:
                key = low.replace("-", "")
                if key in closed:
                    forms[key][low].append(p)
            elif "-" not in low and (low in hyphen_keys or len(low) >= 4):
                forms[low][low].append(p)
            if i + 1 < len(tokens):
                a, b = low, tokens[i + 1].lower()
                if "-" in a or "-" in b or a in _STOPWORDS or b in _STOPWORDS:
                    continue
                key = a + b
                if key in closed or key in hyphen_keys:
                    forms[key][f"{a} {b}"].append(p)
    for variants in forms.values():
        if len(variants) < 2:
            continue
        ranked = sorted(variants.items(), key=lambda kv: (-len(kv[1]), kv[1][0].index))
        main_form = ranked[0][0]
        for form, places in ranked[1:]:
            ctx.report(
                message=f"'{form}' is also written as '{main_form}' in this document.",
                location=paragraph_location(places[0]),
                expected=f"one form: '{main_form}'",
                found=form,
            )


# Re-exported for the profile docs: phrases() is used to read abbreviation headings.
__all__ = ["phrases"]
