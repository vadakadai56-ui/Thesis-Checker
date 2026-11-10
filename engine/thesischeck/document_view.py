"""A read-only snapshot of a Word document, built ONCE per check (BUILD_PROMPT §8).

Rules never look at python-docx objects directly. They get a `DocumentView`: plain,
frozen data (paragraphs, runs, sections) with every value already *resolved*.

"Resolved" matters because Word formatting is layered. The font you see on a
piece of text can come from (first match wins):
    1. the run itself (direct formatting, e.g. you selected text and chose Arial),
    2. the run's character style (and the styles it is "based on"),
    3. the paragraph's style (e.g. "Normal"), and that style's basedOn chain,
    4. the document defaults (<w:docDefaults>),
    5. the theme ("+Body" font = the theme's minor font),
    6. Word's built-in fallback.
`StyleResolver` walks that chain so each rule gets the real, effective value.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .docx_io import safe_parse

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
THEME_RELTYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"


def w(tag: str) -> str:
    """'p' -> '{namespace}p', the form lxml uses for tag names."""
    return f"{{{W_NS}}}{tag}"


def w_attr(el: Any, name: str) -> str | None:
    return None if el is None else el.get(w(name))


# Word's own defaults when nothing at all is specified.
WORD_FALLBACK_FONT = "Times New Roman"
WORD_FALLBACK_SIZE_HALF_PT = 20  # 10 pt

# Inside a paragraph, these subtrees are NOT part of its visible main text:
#   del / moveFrom   = tracked deletions (we check "as if changes were accepted"),
#   txbxContent      = text boxes (their own paragraphs; handled separately later),
#   oMath / oMathPara = equations (skipped by text rules, §9),
#   Fallback         = duplicate legacy copy of drawings.
_SKIP_IN_PARAGRAPH = {
    w("del"),
    w("moveFrom"),
    w("txbxContent"),
    w("pPr"),
    f"{{{M_NS}}}oMath",
    f"{{{M_NS}}}oMathPara",
    f"{{{MC_NS}}}Fallback",
}

# Paragraph styles that are never "body text" (compared case-insensitively by name).
_NON_BODY_STYLE_RE = re.compile(
    r"^(title|subtitle|caption|toc \d|toc heading|table of figures|footnote text|"
    r"endnote text|header|footer)$",
    re.IGNORECASE,
)
_HEADING_NAME_RE = re.compile(r"^heading ([1-9])$", re.IGNORECASE)

WORDS_PER_PAGE_ESTIMATE = 350  # used only when Word saved no page-break hints


# ---------------------------------------------------------------- frozen view types


@dataclass(frozen=True)
class RunView:
    text: str
    font_ascii: str  # font used for plain ASCII characters
    font_hansi: str  # font used for other Latin characters (ā, č, é, …)
    size_pt: float

    def fonts_used(self) -> set[str]:
        """The fonts Word actually uses to draw this run's characters."""
        used: set[str] = set()
        for ch in self.text:
            if ch.isspace():
                continue
            used.add(self.font_ascii if ord(ch) < 128 else self.font_hansi)
        return used


@dataclass(frozen=True)
class ParagraphView:
    index: int
    text: str
    style_id: str | None
    style_name: str | None
    heading_level: int | None  # 1–9 for headings, None for everything else
    section_index: int
    page_estimate: int
    heading_path: tuple[str, ...]
    in_table: bool
    is_body: bool  # ordinary body text (see DocumentBuilder._is_body)
    runs: tuple[RunView, ...]

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def snippet(self) -> str:
        """About 60 characters of the paragraph, for showing the user where it is."""
        text = " ".join(self.text.split())
        return text if len(text) <= 60 else text[:57].rstrip() + "…"


@dataclass(frozen=True)
class SectionView:
    index: int
    page_width: int | None  # twips
    page_height: int | None
    orientation: str  # "portrait" | "landscape"
    margin_top: int | None
    margin_bottom: int | None
    margin_left: int | None
    margin_right: int | None
    gutter: int | None

    @property
    def is_landscape(self) -> bool:
        if self.orientation == "landscape":
            return True
        return bool(self.page_width and self.page_height and self.page_width > self.page_height)


@dataclass(frozen=True)
class DocumentView:
    paragraphs: tuple[ParagraphView, ...]
    sections: tuple[SectionView, ...]
    mirror_margins: bool
    theme_fonts: dict[str, str] = field(default_factory=dict)

    @property
    def headings(self) -> list[ParagraphView]:
        return [p for p in self.paragraphs if p.heading_level is not None and not p.is_empty]

    @property
    def body_paragraphs(self) -> list[ParagraphView]:
        return [p for p in self.paragraphs if p.is_body]

    def first_paragraph_of_section(self, section_index: int) -> ParagraphView | None:
        for p in self.paragraphs:
            if p.section_index == section_index:
                return p
        return None

    @property
    def stats(self) -> dict[str, int]:
        words = sum(len(p.text.split()) for p in self.paragraphs)
        pages = self.paragraphs[-1].page_estimate if self.paragraphs else 0
        return {"paragraphs": len(self.paragraphs), "pages_estimate": pages, "words": words}


# ------------------------------------------------------------------ style resolving


class StyleResolver:
    """Answers "what font / size does this run really have?" by walking Word's layers."""

    def __init__(self, styles_root: Any, theme_root: Any | None) -> None:
        self.styles: dict[str, Any] = {}
        self.default_paragraph_style: str | None = None
        if styles_root is not None:
            for style in styles_root.findall(w("style")):
                style_id = w_attr(style, "styleId")
                if style_id:
                    self.styles[style_id] = style
                if w_attr(style, "type") == "paragraph" and w_attr(style, "default") in (
                    "1",
                    "true",
                ):
                    self.default_paragraph_style = style_id
        self.default_rpr = (
            None
            if styles_root is None
            else styles_root.find(f"{w('docDefaults')}/{w('rPrDefault')}/{w('rPr')}")
        )
        self.theme_fonts = _read_theme_fonts(theme_root)

    # -- style chains ---------------------------------------------------------------

    def chain(self, style_id: str | None) -> list[Any]:
        """The style plus everything it is basedOn, nearest first. Loop-safe."""
        result: list[Any] = []
        seen: set[str] = set()
        while style_id and style_id in self.styles and style_id not in seen:
            seen.add(style_id)
            style = self.styles[style_id]
            result.append(style)
            style_id = w_attr(style.find(w("basedOn")), "val")
        return result

    def style_name(self, style_id: str | None) -> str | None:
        style = self.styles.get(style_id or "")
        return w_attr(style.find(w("name")), "val") if style is not None else None

    def paragraph_style_id(self, p_el: Any) -> str | None:
        p_style = p_el.find(f"{w('pPr')}/{w('pStyle')}")
        return w_attr(p_style, "val") or self.default_paragraph_style

    # -- run properties ---------------------------------------------------------------

    def _rpr_layers(self, r_el: Any, para_style_id: str | None) -> list[Any]:
        """All <w:rPr> elements that can affect a run, most specific first."""
        layers: list[Any] = []
        direct = r_el.find(w("rPr"))
        if direct is not None:
            layers.append(direct)
        char_style_id = w_attr(r_el.find(f"{w('rPr')}/{w('rStyle')}"), "val")
        for style in self.chain(char_style_id) + self.chain(para_style_id):
            rpr = style.find(w("rPr"))
            if rpr is not None:
                layers.append(rpr)
        if self.default_rpr is not None:
            layers.append(self.default_rpr)
        return layers

    def _font_from_rfonts(self, rfonts: Any, slot: str) -> str | None:
        """Read one slot ('ascii' or 'hAnsi') of <w:rFonts>; theme attributes win."""
        theme = w_attr(rfonts, f"{slot}Theme")
        if theme:
            # 'minorHAnsi' -> the theme's minor (body) Latin font, 'major…' -> headings.
            key = "major" if theme.startswith("major") else "minor"
            if key in self.theme_fonts:
                return self.theme_fonts[key]
        return w_attr(rfonts, slot)

    def resolve_run(self, r_el: Any, para_style_id: str | None) -> tuple[str, str, float]:
        """Return (ascii font, hAnsi font, size in pt) for a <w:r> element."""
        layers = self._rpr_layers(r_el, para_style_id)
        fonts: dict[str, str | None] = {"ascii": None, "hAnsi": None}
        size_half_pt: int | None = None
        for rpr in layers:
            rfonts = rpr.find(w("rFonts"))
            if rfonts is not None:
                for slot, current in fonts.items():
                    if current is None:
                        fonts[slot] = self._font_from_rfonts(rfonts, slot)
            if size_half_pt is None:
                sz = w_attr(rpr.find(w("sz")), "val")
                if sz and sz.isdigit():
                    size_half_pt = int(sz)
        fallback = self.theme_fonts.get("minor", WORD_FALLBACK_FONT)
        return (
            fonts["ascii"] or fallback,
            fonts["hAnsi"] or fonts["ascii"] or fallback,
            (size_half_pt or WORD_FALLBACK_SIZE_HALF_PT) / 2,
        )

    # -- headings --------------------------------------------------------------------

    def heading_level(self, p_el: Any, style_id: str | None) -> int | None:
        """1–9 if the paragraph is a heading (outline level or 'heading N' style)."""
        lvl = w_attr(p_el.find(f"{w('pPr')}/{w('outlineLvl')}"), "val")
        for style in self.chain(style_id):
            if lvl is not None:
                break
            lvl = w_attr(style.find(f"{w('pPr')}/{w('outlineLvl')}"), "val")
        if lvl is not None and lvl.isdigit():
            # outlineLvl 0 means "level 1"; 9 means "body text".
            return int(lvl) + 1 if int(lvl) < 9 else None
        for style in self.chain(style_id):
            name = w_attr(style.find(w("name")), "val") or ""
            match = _HEADING_NAME_RE.match(name)
            if match:
                return int(match.group(1))
        return None


def _read_theme_fonts(theme_root: Any | None) -> dict[str, str]:
    """{'major': 'Calibri Light', 'minor': 'Calibri'} from theme1.xml (Latin typefaces)."""
    if theme_root is None:
        return {}
    fonts: dict[str, str] = {}
    for key in ("major", "minor"):
        latin = theme_root.find(f".//{{{A_NS}}}{key}Font/{{{A_NS}}}latin")
        if latin is not None and latin.get("typeface"):
            fonts[key] = latin.get("typeface")
    return fonts


# ---------------------------------------------------------------- building the view


def _iter_runs(container: Any):
    """Yield the visible <w:r> elements of a paragraph, skipping deletions, text boxes, maths."""
    for child in container:
        if child.tag in _SKIP_IN_PARAGRAPH:
            continue
        if child.tag == w("r"):
            yield child
        else:
            # hyperlinks, inserted text (w:ins), fields, content controls … contain runs
            yield from _iter_runs(child)


def _run_text(r_el: Any) -> str:
    parts: list[str] = []
    for child in r_el:
        if child.tag == w("t"):
            parts.append(child.text or "")
        elif child.tag in (w("tab"), w("ptab")):
            parts.append("\t")
        elif child.tag in (w("br"), w("cr")):
            parts.append("\n")
        elif child.tag == w("noBreakHyphen"):
            parts.append("-")
    return "".join(parts)


def _iter_block_paragraphs(container: Any, in_table: bool = False):
    """Yield (<w:p>, in_table) in reading order, entering tables and content controls."""
    for child in container:
        if child.tag == w("p"):
            yield child, in_table
        elif child.tag == w("tbl"):
            for row in child.findall(w("tr")):
                for cell in row.findall(w("tc")):
                    yield from _iter_block_paragraphs(cell, True)
        elif child.tag == w("sdt"):
            content = child.find(w("sdtContent"))
            if content is not None:
                yield from _iter_block_paragraphs(content, in_table)
        elif child.tag in (w("ins"), w("customXml"), w("moveTo")):
            yield from _iter_block_paragraphs(child, in_table)


def _int_attr(el: Any, name: str) -> int | None:
    value = w_attr(el, name)
    try:
        return abs(int(value)) if value is not None else None
    except ValueError:
        return None


def _section_view(index: int, sect_pr: Any) -> SectionView:
    pg_sz = sect_pr.find(w("pgSz"))
    pg_mar = sect_pr.find(w("pgMar"))
    return SectionView(
        index=index,
        page_width=_int_attr(pg_sz, "w"),
        page_height=_int_attr(pg_sz, "h"),
        orientation=w_attr(pg_sz, "orient") or "portrait",
        margin_top=_int_attr(pg_mar, "top"),
        margin_bottom=_int_attr(pg_mar, "bottom"),
        margin_left=_int_attr(pg_mar, "left"),
        margin_right=_int_attr(pg_mar, "right"),
        gutter=_int_attr(pg_mar, "gutter"),
    )


def _theme_root(document: Any) -> Any | None:
    for rel in document.part.rels.values():
        if rel.reltype == THEME_RELTYPE and not rel.is_external:
            return safe_parse(rel.target_part.blob)
    return None


def build_view(document: Any, non_body_styles: Iterable[str] = ()) -> DocumentView:
    """Build the DocumentView from a python-docx Document. Reads only; changes nothing.

    `non_body_styles` comes from the profile (`text.non_body_styles`): paragraph
    style names the university deliberately formats differently from body text
    (e.g. RTU's "Code" style is Arial Narrow 11 pt), so the body-text rules skip them.
    """
    extra_non_body = {name.casefold() for name in non_body_styles}
    body = document.element.body
    resolver = StyleResolver(document.styles.element, _theme_root(document))

    # Sections: every <w:sectPr> in the body, in order (but not the "old" copies kept
    # inside <w:sectPrChange> for tracked changes).
    sect_prs = [s for s in body.iter(w("sectPr")) if s.getparent().tag != w("sectPrChange")]
    sections = tuple(_section_view(i, s) for i, s in enumerate(sect_prs))

    p_elements = list(_iter_block_paragraphs(body))
    has_rendered_breaks = any(True for _ in body.iter(w("lastRenderedPageBreak")))

    paragraphs: list[ParagraphView] = []
    section_index = 0
    page = 1
    words_on_page = 0
    heading_stack: list[tuple[int, str]] = []
    seen_first_heading = False

    for index, (p_el, in_table) in enumerate(p_elements):
        style_id = resolver.paragraph_style_id(p_el)
        style_name = resolver.style_name(style_id)
        runs_el = list(_iter_runs(p_el))
        runs = tuple(RunView(_run_text(r), *resolver.resolve_run(r, style_id)) for r in runs_el)
        text = "".join(r.text for r in runs)
        level = None if in_table else resolver.heading_level(p_el, style_id)

        # --- page estimate -----------------------------------------------------------
        if has_rendered_breaks:
            # Word remembers where pages broke the last time it laid out the file.
            page += sum(1 for _ in p_el.iter(w("lastRenderedPageBreak")))
        else:
            page_breaks = [br for br in p_el.iter(w("br")) if w_attr(br, "type") == "page"]
            break_before = p_el.find(f"{w('pPr')}/{w('pageBreakBefore')}") is not None
            explicit = len(page_breaks) + int(break_before)
            words_on_page += len(text.split())
            if explicit:
                page += explicit
                words_on_page = 0
            elif words_on_page > WORDS_PER_PAGE_ESTIMATE:
                page += 1
                words_on_page -= WORDS_PER_PAGE_ESTIMATE

        # --- heading path (e.g. ("1 Theory", "1.1 Methods")) ------------------------
        if level is not None and text.strip():
            seen_first_heading = True
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, " ".join(text.split())))
        path = tuple(t for _, t in heading_stack)

        is_body = (
            seen_first_heading  # text before the first heading = title page (TITLE rules)
            and level is None
            and not in_table  # tables may legitimately use smaller text
            and bool(text.strip())
            and not _NON_BODY_STYLE_RE.match(style_name or "")
            and (style_name or "").casefold() not in extra_non_body
        )

        paragraphs.append(
            ParagraphView(
                index=index,
                text=text,
                style_id=style_id,
                style_name=style_name,
                heading_level=level,
                section_index=min(section_index, max(len(sections) - 1, 0)),
                page_estimate=page,
                heading_path=path,
                in_table=in_table,
                is_body=is_body,
                runs=runs,
            )
        )
        # A <w:sectPr> inside a paragraph's properties ENDS a section at that paragraph.
        if p_el.find(f"{w('pPr')}/{w('sectPr')}") is not None:
            section_index += 1

    settings = document.settings.element
    return DocumentView(
        paragraphs=tuple(paragraphs),
        sections=sections,
        mirror_margins=settings.find(w("mirrorMargins")) is not None,
        theme_fonts=dict(resolver.theme_fonts),
    )
