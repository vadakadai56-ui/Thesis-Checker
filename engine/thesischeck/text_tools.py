"""Text helpers: sentences, in-text citations and reference-list entries.

All of this is pattern matching (regular expressions) on plain text. It is a
best effort: it finds the common forms, e.g. "(Example, 2024)",
"(Sample and Person, 2023; Other et al., 2020, p. 5)", "Example (2024)" and "[3]".
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .regions import strip_accents

YEAR = r"(?:1[5-9]|20)\d{2}[a-z]?"
_PAREN_RE = re.compile(rf"\(([^()]*\b{YEAR}\b[^()]*)\)")
_NARRATIVE_RE = re.compile(
    rf"\b([A-ZĀ-Ž][\w'’\-]+(?:\s+(?:et al\.|and|un|&)\s*(?:[A-ZĀ-Ž][\w'’\-]+)?)?)\s+\(({YEAR})\)"
)
_NUMERIC_RE = re.compile(r"\[(\d+(?:\s*[-–,]\s*\d+)*)\]")
_ITEM_RE = re.compile(rf"^(?P<authors>.+?),?\s+(?P<year>{YEAR})\b(?P<rest>.*)$")
# The strict author–date form: "Author, 2024", "Author et al., 2024, p. 5".
_STRICT_ITEM_RE = re.compile(
    rf"^(?:(?:see|e\.g\.,?|cf\.|sk\.)\s+)?[^,;()\d]+?,\s{YEAR}"
    r"(?:,\s*(?:p|pp|lpp)\.\s*[\d–\-]+)?$",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(r"^(?:see|e\.g\.,?|cf\.|sk\.)\s+", re.IGNORECASE)
_KEY_TOKEN_RE = re.compile(r"[\w/\-’']+")
URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
ACCESS_DATE_RE = re.compile(
    r"(accessed|viewed|retrieved|skatīts|citēts)\b[^\d\]]{0,20}\d{1,2}\.\s?\d{1,2}\.\s?\d{4}",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?…])[\"”“»]?\s+(?=[A-ZĀ-Ž\"„“«(\[])")


def key_token(text: str) -> str:
    """'Sample and Person' -> 'sample'; accents removed so 'Bērziņš' == 'Berzins'."""
    match = _KEY_TOKEN_RE.search(text)
    return strip_accents(match.group(0)).casefold() if match else ""


@dataclass(frozen=True)
class Citation:
    text: str  # the item as written, e.g. "Example, 2024"
    key: str  # first author's surname, normalised
    year: str  # "2024" (letter suffix removed)
    strict: bool  # written in the strict "(Author, 2024)" form


def author_date_citations(text: str) -> list[Citation]:
    """All author–date citations in a piece of text."""
    found: list[Citation] = []
    for group in _PAREN_RE.finditer(text):
        for item in re.split(r";\s*", group.group(1)):
            item = item.strip()
            match = _ITEM_RE.match(_PREFIX_RE.sub("", item))
            if not match:
                continue
            authors = match.group("authors").strip()
            if not authors[:1].isupper():
                continue  # "(in 2020 …)" is not a citation
            found.append(
                Citation(
                    text=item,
                    key=key_token(authors),
                    year=match.group("year")[:4],
                    strict=bool(_STRICT_ITEM_RE.match(item)),
                )
            )
    for match in _NARRATIVE_RE.finditer(text):
        found.append(Citation(match.group(0), key_token(match.group(1)), match.group(2)[:4], True))
    return found


def numeric_citations(text: str) -> list[int]:
    numbers: list[int] = []
    for group in _NUMERIC_RE.finditer(text):
        for part in re.split(r"\s*,\s*", group.group(1)):
            if re.search(r"[-–]", part):
                a, b = (int(x) for x in re.split(r"\s*[-–]\s*", part)[:2])
                numbers.extend(range(min(a, b), max(a, b) + 1))
            else:
                numbers.append(int(part))
    return numbers


def has_any_citation(text: str) -> bool:
    return bool(author_date_citations(text) or _NUMERIC_RE.search(text))


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END_RE.split(" ".join(text.split())) if s.strip()]


@dataclass(frozen=True)
class RefEntry:
    index: int  # paragraph index
    text: str
    key: str
    year: str | None
    urls: tuple[str, ...]


def parse_entry(index: int, text: str) -> RefEntry:
    clean = " ".join(text.split())
    clean = re.sub(r"^\[?\d+[.\])]\s*", "", clean)  # drop "[1] " / "1. " numbering
    year = re.search(rf"\b({YEAR})\b", clean)
    return RefEntry(
        index=index,
        text=clean,
        key=key_token(clean),
        year=year.group(1)[:4] if year else None,
        urls=tuple(URL_RE.findall(clean)),
    )


def sort_key(text: str) -> str:
    return strip_accents(" ".join(text.split())).casefold()


# ------------------------------------------------------------------ quotations

_QUOTE_RE = re.compile(r"„([^“”\"]+)[“”\"]|“([^”]+)”|\"([^\"]+)\"|«([^»]+)»")


def quotations(text: str) -> list[tuple[int, int, str]]:
    """(start, end, quoted text) for every quoted passage."""
    result = []
    for match in _QUOTE_RE.finditer(text):
        quoted = next(g for g in match.groups() if g is not None)
        result.append((match.start(), match.end(), quoted))
    return result
