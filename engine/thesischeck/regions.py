"""Find the named parts of a thesis: title page, Abstract, Introduction, References, …

The profile says how each part is recognised (`structure.sections`): by its heading
text (in any of the listed spellings/languages) or by how its first paragraph starts.
A part runs from its heading to the next recognised part or level-1 heading.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .document_view import DocumentView, ParagraphView
from .model import TODO

WORDS_PER_PAGE = 350  # rough page estimate when Word saved no page-break hints


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm(text: str) -> str:
    """Normalise a heading for comparison: '2.1. Results ' -> 'results'."""
    text = " ".join(text.split()).casefold()
    text = re.sub(r"^\d+(\.\d+)*\.?\s*", "", text)
    return text.strip(" .:;")


def phrases(values: Any) -> list[str]:
    """A list of phrases from the profile, ignoring TODO placeholders."""
    if isinstance(values, str):
        values = [values]
    return [v for v in (values or []) if isinstance(v, str) and v != TODO]


@dataclass(frozen=True)
class Region:
    name: str
    marker: int | None  # index of the heading/first paragraph that starts it
    start: int  # first paragraph index belonging to the region
    end: int  # one past the last paragraph index


class Regions:
    """The thesis parts found in one document (built once per check)."""

    def __init__(self, view: DocumentView, structure: dict[str, Any] | None) -> None:
        self.view = view
        self.structure = structure or {}
        self.sections_cfg: dict[str, dict[str, Any]] = {
            k: v for k, v in (self.structure.get("sections") or {}).items() if isinstance(v, dict)
        }
        self.level1 = [p.index for p in view.headings if p.heading_level == 1]
        self.regions: dict[str, Region] = {}
        self._find_markers()
        self.title_page = self._find_title_page()

    # -- detection -------------------------------------------------------------------

    def _candidates(self) -> list[ParagraphView]:
        """Paragraphs that could start a part: not in tables, TOC entries or captions."""
        result = []
        for p in self.view.paragraphs:
            if p.is_empty or p.in_table or p.is_caption_like:
                continue
            if any(re.match(r"^\s*TOC\b", instr, re.I) for _, instr in p.fields):
                continue
            if (p.style_name or "").casefold().startswith("toc "):
                continue
            result.append(p)
        return result

    def _find_markers(self) -> None:
        markers: dict[str, int] = {}
        candidates = self._candidates()

        def matches(name: str, p: ParagraphView) -> bool:
            cfg = self.sections_cfg[name]
            text = norm(p.text)
            headings = {norm(h) for h in phrases(cfg.get("headings"))}
            starts = [norm(s) for s in phrases(cfg.get("starts_with"))]
            short = p.heading_level is not None or len(text.split()) <= 6
            return (bool(headings) and text in headings and short) or any(
                text.startswith(s) for s in starts
            )

        # Pass 1: real headings win (e.g. "INTRODUCTION" in a heading style).
        for name in self.sections_cfg:
            for p in candidates:
                if p.heading_level is not None and matches(name, p):
                    markers[name] = p.index
                    break
        # Pass 2: other paragraphs, but never inside the table of contents, where
        # the same words appear as (hand-typed) contents lines.
        toc_start = markers.get("toc")
        toc_end = min(
            (i for i in self.level1 if toc_start is not None and i > toc_start), default=None
        )
        for name in self.sections_cfg:
            if name in markers:
                continue
            for p in candidates:
                if toc_start is not None and toc_end is not None and toc_start <= p.index < toc_end:
                    continue
                if matches(name, p):
                    markers[name] = p.index
                    break

        ordered = sorted(markers.items(), key=lambda kv: kv[1])
        boundaries = sorted(set(markers.values()) | set(self.level1))
        n = len(self.view.paragraphs)
        for name, index in ordered:
            later = [b for b in boundaries if b > index]
            end = later[0] if later else n
            self.regions[name] = Region(name, index, index + 1, end)

    def _find_title_page(self) -> Region | None:
        view = self.view
        first_marker = min(
            [r.marker for r in self.regions.values() if r.marker is not None] + self.level1,
            default=len(view.paragraphs),
        )
        end = first_marker
        if len(view.sections) > 1:
            # If the first Word section ends before the first part, it IS the title page.
            last_of_first = max(
                (p.index for p in view.paragraphs if p.section_index == 0), default=-1
            )
            if last_of_first < first_marker:
                end = last_of_first + 1
        if end <= 0 or not any(not p.is_empty for p in view.paragraphs[:end]):
            return None
        return Region("title_page", None, 0, end)

    # -- queries ---------------------------------------------------------------------

    def get(self, name: str) -> Region | None:
        if name == "title_page":
            return self.title_page
        return self.regions.get(name)

    def paragraphs(self, name_or_region: str | Region) -> list[ParagraphView]:
        region = self.get(name_or_region) if isinstance(name_or_region, str) else name_or_region
        if region is None:
            return []
        return [p for p in self.view.paragraphs[region.start : region.end] if not p.is_empty]

    def contains(self, name: str, index: int) -> bool:
        region = self.get(name)
        if region is None:
            return False
        start = region.marker if region.marker is not None else region.start
        return start <= index < region.end

    def after_marker(self, name: str, index: int) -> bool:
        """True if `index` is at or after where part `name` starts (e.g. appendices)."""
        region = self.get(name)
        return region is not None and region.marker is not None and index >= region.marker

    def chapters(self) -> list[ParagraphView]:
        """Numbered level-1 headings (the main chapters)."""
        return [
            self.view.paragraphs[i] for i in self.level1 if self.view.paragraphs[i].heading_number
        ]

    def chapter_of(self, index: int) -> ParagraphView | None:
        """The level-1 heading a paragraph belongs to."""
        before = [i for i in self.level1 if i <= index]
        return self.view.paragraphs[before[-1]] if before else None

    def chapter_region(self, heading_index: int) -> Region:
        later = [i for i in self.level1 if i > heading_index]
        return Region(
            "chapter",
            heading_index,
            heading_index + 1,
            later[0] if later else len(self.view.paragraphs),
        )

    def position(self, name: str) -> int | None:
        """Where a part starts (for the order check). 'chapters' = first numbered chapter."""
        if name == "title_page":
            return 0 if self.title_page else None
        if name == "chapters":
            chapters = self.chapters()
            return chapters[0].index if chapters else None
        region = self.regions.get(name)
        return region.marker if region else None

    def pages(self, region: Region) -> float:
        """Estimated length of a region in pages."""
        paras = self.view.paragraphs[region.start : region.end]
        if not paras:
            return 0.0
        if self.view.has_rendered_breaks:
            first = self.view.paragraphs[region.marker or region.start].page_estimate
            return float(paras[-1].page_estimate - first + 1)
        words = sum(len(p.text.split()) for p in paras)
        return words / WORDS_PER_PAGE

    def words(self, region: Region) -> int:
        return sum(len(p.text.split()) for p in self.view.paragraphs[region.start : region.end])
