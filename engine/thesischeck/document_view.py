"""A read-only snapshot of a Word document, built ONCE per check (BUILD_PROMPT §8).

Rules never look at python-docx objects directly. They get a `DocumentView`: plain,
frozen data (paragraphs, runs, sections, tables, …) with every value already
*resolved*.

"Resolved" matters because Word formatting is layered. The font you see on a
piece of text can come from (first match wins):
    1. the run itself (direct formatting, e.g. you selected text and chose Arial),
    2. the run's character style (and the styles it is "based on"),
    3. the paragraph's style (e.g. "Normal"), and that style's basedOn chain,
    4. the document defaults (<w:docDefaults>),
    5. the theme ("+Body" font = the theme's minor font),
    6. Word's built-in fallback.
Paragraph settings (alignment, spacing, indents) work the same way, with list
numbering sitting between the paragraph and its style. `StyleResolver` walks
these chains so each rule gets the real, effective value.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

from .docx_io import safe_parse

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
V_NS = "urn:schemas-microsoft-com:vml"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
RELTYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"


def w(tag: str) -> str:
    """'p' -> '{namespace}p', the form lxml uses for tag names."""
    return f"{{{W_NS}}}{tag}"


def w_attr(el: Any, name: str) -> str | None:
    return None if el is None else el.get(w(name))


# Word's own defaults when nothing at all is specified.
WORD_FALLBACK_FONT = "Times New Roman"
WORD_FALLBACK_SIZE_HALF_PT = 20  # 10 pt
SINGLE_LINE = 240  # line spacing is stored in 240ths of a line ("auto" rule)

# Inside a paragraph, these subtrees are NOT part of its visible main text:
#   del / moveFrom   = tracked deletions (we check "as if changes were accepted"),
#   txbxContent      = text boxes (their own paragraphs; collected separately),
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
    r"endnote text|header|footer|bibliography)$",
    re.IGNORECASE,
)
_HEADING_NAME_RE = re.compile(r"^heading ([1-9])$", re.IGNORECASE)
_TYPED_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)(\.?)(?=\s)")
# Caption words in English and Latvian, used to recognise captions typed by hand.
_GENERIC_CAPTION_ROOTS = ("fig", "table", "tab", "att", "pielikum")

WORDS_PER_PAGE_ESTIMATE = 350  # used only when Word saved no page-break hints

_ALIGN = {
    "both": "justified",
    "distribute": "justified",
    "left": "left",
    "start": "left",
    "center": "center",
    "right": "right",
    "end": "right",
}
_TRUE_VALUES = {None, "1", "true", "on"}


# ---------------------------------------------------------------- frozen view types


@dataclass(frozen=True)
class RunView:
    text: str
    font_ascii: str  # font used for plain ASCII characters
    font_hansi: str  # font used for other Latin characters (ā, č, é, …)
    size_pt: float
    bold: bool = False
    italic: bool = False
    caps: bool = False
    underline: bool = False
    color: str | None = None
    lang: str | None = None
    # Properties set by DIRECT formatting that differ from what the style gives
    # (e.g. {"color", "bold"}). Used by TEXT-07.
    direct: frozenset[str] = frozenset()

    def fonts_used(self) -> set[str]:
        """The fonts Word actually uses to draw this run's characters."""
        used: set[str] = set()
        for ch in self.text:
            if ch.isspace():
                continue
            used.add(self.font_ascii if ord(ch) < 128 else self.font_hansi)
        return used


@dataclass(frozen=True)
class NumberingView:
    """Word list numbering on a paragraph (e.g. a numbered heading or a bullet)."""

    num_id: str
    ilvl: int
    num_fmt: str  # decimal, bullet, lowerLetter, …
    label: str  # what Word shows, e.g. "1.2." or "•"


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
    is_body: bool  # ordinary body text (see _is_body)
    runs: tuple[RunView, ...]
    # Resolved paragraph formatting (twips unless stated otherwise).
    alignment: str = "left"  # left | center | right | justified
    line_rule: str = "auto"  # auto (multiple of lines) | exact | atLeast
    line_value: int = SINGLE_LINE  # 240ths of a line for "auto", else twips
    space_before: int = 0
    space_after: int = 0
    indent_left: int = 0
    first_line: int = 0  # positive = first-line indent, negative = hanging
    tabs: tuple[tuple[str, int], ...] = ()  # (alignment, position) of custom tab stops
    page_break_before: bool = False  # the "page break before" paragraph setting
    starts_with_page_break: bool = False  # a manual page break before any text
    has_page_break: bool = False  # any manual page break in the paragraph
    ends_section: bool = False
    section_break_type: str | None = None  # nextPage | continuous | … when ends_section
    has_image: bool = False
    has_math: bool = False
    has_note_ref: bool = False  # contains a footnote/endnote reference mark
    numbering: NumberingView | None = None
    heading_number: str | None = None  # "1.2" for "1.2. Title" (typed or Word list)
    heading_number_dot: bool = False  # the number is followed by a full stop
    heading_number_source: str | None = None  # typed | list
    table_index: int | None = None
    lang: str | None = None  # "en", "lv", … (primary language subtag)
    fields: tuple[tuple[int, str], ...] = ()  # (field id, instruction) of fields touching it
    is_caption_like: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @property
    def clean_text(self) -> str:
        """Text with all whitespace (tabs, line breaks) collapsed to single spaces."""
        return " ".join(self.text.split())

    @property
    def snippet(self) -> str:
        """About 60 characters of the paragraph, for showing the user where it is."""
        text = self.clean_text
        return text if len(text) <= 60 else text[:57].rstrip() + "…"

    @property
    def line_spacing_lines(self) -> float | None:
        """Line spacing as a multiple (1.5 = 1.5 lines), or None if exact/at-least."""
        return self.line_value / SINGLE_LINE if self.line_rule == "auto" else None


@dataclass(frozen=True)
class HeaderFooterView:
    kind: str  # header | footer
    text: str
    has_page_field: bool
    page_alignment: str | None  # left | center | right (where the number appears)
    page_format_switch: str | None  # e.g. "roman" from { PAGE \* roman }


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
    title_page: bool = False  # "Different first page" is on
    page_number_start: int | None = None
    page_number_format: str | None = None  # decimal, lowerRoman, … (None = decimal)
    break_type: str = "nextPage"
    # Effective (inherited) headers/footers: keys "default", "first", "even".
    headers: dict[str, HeaderFooterView | None] = field(default_factory=dict)
    footers: dict[str, HeaderFooterView | None] = field(default_factory=dict)

    @property
    def is_landscape(self) -> bool:
        if self.orientation == "landscape":
            return True
        return bool(self.page_width and self.page_height and self.page_width > self.page_height)


@dataclass(frozen=True)
class TableView:
    index: int
    first_paragraph: int  # index of the first paragraph inside the table
    last_paragraph: int
    before_paragraph: int | None  # last paragraph before the table
    after_paragraph: int | None  # first paragraph after the table


@dataclass(frozen=True)
class FieldView:
    id: int
    instruction: str  # e.g. 'TOC \o "1-3" \h \z \u'
    paragraph_indices: tuple[int, ...]


@dataclass(frozen=True)
class DocumentView:
    paragraphs: tuple[ParagraphView, ...]
    sections: tuple[SectionView, ...]
    mirror_margins: bool
    theme_fonts: dict[str, str] = field(default_factory=dict)
    tables: tuple[TableView, ...] = ()
    fields: tuple[FieldView, ...] = ()
    footnotes: tuple[str, ...] = ()
    textboxes: tuple[tuple[int, str], ...] = ()  # (paragraph index, text)
    has_rendered_breaks: bool = False
    has_tracked_changes: bool = False
    update_fields_on_open: bool = False
    even_and_odd_headers: bool = False

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

    def fields_named(self, name: str) -> list[FieldView]:
        """Fields whose instruction starts with `name` (e.g. "TOC")."""
        pattern = re.compile(rf"^\s*{name}(\s|\\|$)", re.IGNORECASE)
        return [f for f in self.fields if pattern.match(f.instruction)]

    @property
    def stats(self) -> dict[str, int]:
        words = sum(len(p.text.split()) for p in self.paragraphs)
        pages = self.paragraphs[-1].page_estimate if self.paragraphs else 0
        return {"paragraphs": len(self.paragraphs), "pages_estimate": pages, "words": words}


# ------------------------------------------------------------------ style resolving


def _toggle(el: Any) -> bool | None:
    """Word on/off properties: <w:b/> is on, <w:b w:val="0"/> is off, absent = unknown."""
    if el is None:
        return None
    return w_attr(el, "val") in _TRUE_VALUES


class StyleResolver:
    """Answers "what does this run/paragraph really look like?" by walking Word's layers."""

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
        defaults = None if styles_root is None else styles_root.find(w("docDefaults"))
        self.default_rpr = (
            None if defaults is None else defaults.find(f"{w('rPrDefault')}/{w('rPr')}")
        )
        self.default_ppr = (
            None if defaults is None else defaults.find(f"{w('pPrDefault')}/{w('pPr')}")
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

    def _rpr_layers(self, r_el: Any, para_style_id: str | None, direct: bool) -> list[Any]:
        """All <w:rPr> elements that can affect a run, most specific first."""
        layers: list[Any] = []
        rpr = r_el.find(w("rPr"))
        if direct and rpr is not None:
            layers.append(rpr)
        char_style_id = w_attr(r_el.find(f"{w('rPr')}/{w('rStyle')}"), "val")
        for style in self.chain(char_style_id) + self.chain(para_style_id):
            style_rpr = style.find(w("rPr"))
            if style_rpr is not None:
                layers.append(style_rpr)
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

    def _run_props(self, layers: list[Any]) -> dict[str, Any]:
        fonts: dict[str, str | None] = {"ascii": None, "hAnsi": None}
        props: dict[str, Any] = {}
        for rpr in layers:
            rfonts = rpr.find(w("rFonts"))
            if rfonts is not None:
                for slot, current in fonts.items():
                    if current is None:
                        fonts[slot] = self._font_from_rfonts(rfonts, slot)
            for tag in ("b", "i", "caps"):
                if tag not in props:
                    value = _toggle(rpr.find(w(tag)))
                    if value is not None:
                        props[tag] = value
            for tag in ("sz", "u", "color", "lang", "highlight"):
                el = rpr.find(w(tag))
                if tag not in props and el is not None:
                    props[tag] = w_attr(el, "val")
        fallback = self.theme_fonts.get("minor", WORD_FALLBACK_FONT)
        size = props.get("sz")
        color = props.get("color")
        return {
            "font_ascii": fonts["ascii"] or fallback,
            "font_hansi": fonts["hAnsi"] or fonts["ascii"] or fallback,
            "size_pt": (int(size) if size and size.isdigit() else WORD_FALLBACK_SIZE_HALF_PT) / 2,
            "bold": props.get("b", False),
            "italic": props.get("i", False),
            "caps": props.get("caps", False),
            "underline": props.get("u") not in (None, "none"),
            "color": None if color in (None, "auto", "000000") else color,
            "highlight": props.get("highlight") not in (None, "none"),
            "lang": props.get("lang"),
        }

    def resolve_run(self, r_el: Any, para_style_id: str | None, text: str) -> RunView:
        full = self._run_props(self._rpr_layers(r_el, para_style_id, direct=True))
        base = self._run_props(self._rpr_layers(r_el, para_style_id, direct=False))
        compared = ("font_ascii", "size_pt", "bold", "italic", "underline", "color", "caps")
        direct = frozenset(k for k in (*compared, "highlight") if full[k] != base[k])
        return RunView(
            text=text,
            font_ascii=full["font_ascii"],
            font_hansi=full["font_hansi"],
            size_pt=full["size_pt"],
            bold=full["bold"],
            italic=full["italic"],
            caps=full["caps"],
            underline=full["underline"],
            color=full["color"],
            lang=full["lang"],
            direct=direct,
        )

    # -- paragraph properties -----------------------------------------------------------

    def ppr_layers(self, p_el: Any, style_id: str | None, numbering_ppr: Any | None) -> list:
        """All <w:pPr> that can affect a paragraph: direct, list level, styles, defaults."""
        layers: list[Any] = []
        direct = p_el.find(w("pPr"))
        if direct is not None:
            layers.append(direct)
        if numbering_ppr is not None:
            layers.append(numbering_ppr)
        for style in self.chain(style_id):
            ppr = style.find(w("pPr"))
            if ppr is not None:
                layers.append(ppr)
        if self.default_ppr is not None:
            layers.append(self.default_ppr)
        return layers

    @staticmethod
    def _first_attr(layers: list[Any], tag: str, attrs: Iterable[str]) -> str | None:
        for ppr in layers:
            el = ppr.find(w(tag))
            for attr in attrs:
                value = w_attr(el, attr)
                if value is not None:
                    return value
        return None

    def paragraph_props(self, layers: list[Any]) -> dict[str, Any]:
        def num(tag: str, attrs: Iterable[str], default: int) -> int:
            value = self._first_attr(layers, tag, attrs)
            try:
                return int(value) if value is not None else default
            except ValueError:
                return default

        jc = self._first_attr(layers, "jc", ["val"])
        first_line = 0
        for ppr in layers:  # firstLine and hanging are one setting: nearest layer wins
            ind = ppr.find(w("ind"))
            if w_attr(ind, "hanging") is not None:
                first_line = -int(w_attr(ind, "hanging") or 0)
                break
            if w_attr(ind, "firstLine") is not None:
                first_line = int(w_attr(ind, "firstLine") or 0)
                break
        page_break = None
        for ppr in layers:
            page_break = _toggle(ppr.find(w("pageBreakBefore")))
            if page_break is not None:
                break
        tabs: tuple[tuple[str, int], ...] = ()
        for ppr in layers:
            tabs_el = ppr.find(w("tabs"))
            if tabs_el is not None:
                tabs = tuple(
                    sorted(
                        (
                            (w_attr(t, "val") or "left", int(w_attr(t, "pos") or 0))
                            for t in tabs_el.findall(w("tab"))
                            if w_attr(t, "val") != "clear"
                        ),
                        key=lambda t: t[1],
                    )
                )
                break
        return {
            "alignment": _ALIGN.get(jc or "left", "left"),
            "line_rule": self._first_attr(layers, "spacing", ["lineRule"]) or "auto",
            "line_value": num("spacing", ["line"], SINGLE_LINE),
            "space_before": num("spacing", ["before"], 0),
            "space_after": num("spacing", ["after"], 0),
            "indent_left": num("ind", ["left", "start"], 0),
            "first_line": first_line,
            "tabs": tabs,
            "page_break_before": bool(page_break),
        }

    def num_pr(self, p_el: Any, style_id: str | None) -> tuple[str, int] | None:
        """(numId, ilvl) of the paragraph's list numbering, from the paragraph or its style."""
        num_id = ilvl = None
        direct = p_el.find(f"{w('pPr')}/{w('numPr')}")
        if direct is not None:
            num_id = w_attr(direct.find(w("numId")), "val")
            ilvl = w_attr(direct.find(w("ilvl")), "val")
        if num_id is None:
            for style in self.chain(style_id):
                style_num = style.find(f"{w('pPr')}/{w('numPr')}")
                if style_num is not None:
                    num_id = w_attr(style_num.find(w("numId")), "val")
                    ilvl = ilvl or w_attr(style_num.find(w("ilvl")), "val")
                    if num_id is not None:
                        break
        if num_id in (None, "0"):
            return None
        return num_id, int(ilvl) if ilvl and ilvl.isdigit() else 0

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


# -------------------------------------------------------------------- list numbering


def _format_number(value: int, fmt: str) -> str:
    if fmt in ("lowerLetter", "upperLetter"):
        letters = ""
        n = value
        while n > 0:
            n, rem = divmod(n - 1, 26)
            letters = chr(97 + rem) + letters
        return letters.upper() if fmt == "upperLetter" else letters
    if fmt in ("lowerRoman", "upperRoman"):
        numerals = [
            (1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
            (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"),
        ]  # fmt: skip
        out, n = "", value
        for amount, numeral in numerals:
            while n >= amount:
                out += numeral
                n -= amount
        return out.upper() if fmt == "upperRoman" else out
    return str(value)


class NumberingResolver:
    """Works out the label Word shows for numbered paragraphs ("1.2.", "a)", "•")."""

    def __init__(self, numbering_root: Any | None) -> None:
        self.abstract: dict[str, Any] = {}
        self.nums: dict[str, tuple[str | None, dict[int, Any], dict[int, int]]] = {}
        self.counters: dict[str, list[int | None]] = {}
        if numbering_root is None:
            return
        for abstract in numbering_root.findall(w("abstractNum")):
            self.abstract[w_attr(abstract, "abstractNumId") or ""] = abstract
        for num in numbering_root.findall(w("num")):
            abstract_id = w_attr(num.find(w("abstractNumId")), "val")
            overrides: dict[int, Any] = {}
            starts: dict[int, int] = {}
            for override in num.findall(w("lvlOverride")):
                ilvl = int(w_attr(override, "ilvl") or 0)
                if override.find(w("lvl")) is not None:
                    overrides[ilvl] = override.find(w("lvl"))
                start = w_attr(override.find(w("startOverride")), "val")
                if start and start.isdigit():
                    starts[ilvl] = int(start)
            self.nums[w_attr(num, "numId") or ""] = (abstract_id, overrides, starts)

    def level(self, num_id: str, ilvl: int) -> Any | None:
        if num_id not in self.nums:
            return None
        abstract_id, overrides, _ = self.nums[num_id]
        if ilvl in overrides:
            return overrides[ilvl]
        abstract = self.abstract.get(abstract_id or "")
        if abstract is None:
            return None
        for lvl in abstract.findall(w("lvl")):
            if w_attr(lvl, "ilvl") == str(ilvl):
                return lvl
        return None

    def _start(self, num_id: str, ilvl: int) -> int:
        starts = self.nums.get(num_id, (None, {}, {}))[2]
        if ilvl in starts:
            return starts[ilvl]
        start = w_attr(getattr(self.level(num_id, ilvl), "find", lambda _: None)(w("start")), "val")
        return int(start) if start and start.isdigit() else 1

    def next_label(self, num_id: str, ilvl: int) -> NumberingView | None:
        """Advance the counter for (num_id, ilvl) and return the resulting label."""
        lvl = self.level(num_id, ilvl)
        if lvl is None:
            return None
        counters = self.counters.setdefault(num_id, [None] * 9)
        counters[ilvl] = self._start(num_id, ilvl) if counters[ilvl] is None else counters[ilvl] + 1
        for deeper in range(ilvl + 1, 9):
            counters[deeper] = None
        num_fmt = w_attr(lvl.find(w("numFmt")), "val") or "decimal"
        text = w_attr(lvl.find(w("lvlText")), "val") or ""
        if num_fmt != "bullet":
            for k in range(9):
                if f"%{k + 1}" in text:
                    k_lvl = self.level(num_id, k)
                    k_fmt = w_attr(getattr(k_lvl, "find", lambda _: None)(w("numFmt")), "val")
                    value = counters[k] if counters[k] is not None else self._start(num_id, k)
                    text = text.replace(f"%{k + 1}", _format_number(value, k_fmt or "decimal"))
        return NumberingView(num_id=num_id, ilvl=ilvl, num_fmt=num_fmt, label=text)


# ---------------------------------------------------------------- building the view


def _walk_paragraph(container: Any) -> Iterator[tuple[str, Any]]:
    """Yield ('run', r) and ('simple_field', fldSimple start/end) events in reading order."""
    for child in container:
        if child.tag in _SKIP_IN_PARAGRAPH:
            continue
        if child.tag == w("r"):
            yield "run", child
        elif child.tag == w("fldSimple"):
            yield "simple_begin", child
            yield from _walk_paragraph(child)
            yield "simple_end", child
        else:
            # hyperlinks, inserted text (w:ins), content controls … contain runs
            yield from _walk_paragraph(child)


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


@dataclass
class _Block:
    p_el: Any
    in_table: bool
    table_index: int | None


def _iter_blocks(container: Any, state: dict[str, Any], in_table: bool = False, table=None):
    """Yield _Block for every paragraph in reading order, entering tables and content
    controls. Top-level tables get an index in `state["tables"]`."""
    for child in container:
        if child.tag == w("p"):
            yield _Block(child, in_table, table)
        elif child.tag == w("tbl"):
            index = table
            if not in_table:  # only top-level tables are "tables" for the rules
                index = len(state["tables"])
                state["tables"].append(index)
            for row in child.findall(w("tr")):
                for cell in row.findall(w("tc")):
                    yield from _iter_blocks(cell, state, True, index)
        elif child.tag == w("sdt"):
            content = child.find(w("sdtContent"))
            if content is not None:
                yield from _iter_blocks(content, state, in_table, table)
        elif child.tag in (w("ins"), w("customXml"), w("moveTo")):
            yield from _iter_blocks(child, state, in_table, table)


class _FieldTracker:
    """Follows Word fields ({ TOC … }, { PAGE }, …) that can span several paragraphs."""

    def __init__(self) -> None:
        self.stack: list[dict[str, Any]] = []
        self.next_id = 0
        self.finished: list[tuple[int, str]] = []

    def begin(self, instruction: str = "") -> None:
        self.stack.append({"id": self.next_id, "instr": [instruction]})
        self.next_id += 1

    def end(self) -> None:
        if self.stack:
            top = self.stack.pop()
            self.finished.append((top["id"], "".join(top["instr"]).strip()))

    def open_fields(self) -> list[tuple[int, str]]:
        return [(f["id"], "".join(f["instr"]).strip()) for f in self.stack]

    def run(self, r_el: Any) -> None:
        for child in r_el:
            if child.tag == w("fldChar"):
                kind = w_attr(child, "fldCharType")
                if kind == "begin":
                    self.begin()
                elif kind == "end":
                    self.end()
            elif child.tag == w("instrText") and self.stack:
                self.stack[-1]["instr"].append(child.text or "")


def _int_attr(el: Any, name: str) -> int | None:
    value = w_attr(el, name)
    try:
        return abs(int(value)) if value is not None else None
    except ValueError:
        return None


def _part_root(document: Any, rel_id: str | None) -> Any | None:
    if not rel_id:
        return None
    part = document.part.related_parts.get(rel_id)
    if part is None:
        return None
    element = getattr(part, "element", None)
    return element if element is not None else safe_parse(part.blob)


def _related_root(document: Any, reltype_suffix: str) -> Any | None:
    for rel in document.part.rels.values():
        if rel.reltype == RELTYPE + reltype_suffix and not rel.is_external:
            part = rel.target_part
            element = getattr(part, "element", None)
            return element if element is not None else safe_parse(part.blob)
    return None


_PAGE_FIELD_RE = re.compile(r"^\s*PAGE(\s|\\|$)", re.IGNORECASE)
_FORMAT_SWITCH_RE = re.compile(r"\\\*\s*(roman|alphabetic|arabic)", re.IGNORECASE)


def _header_footer_view(root: Any, kind: str, resolver: StyleResolver) -> HeaderFooterView:
    """Find the page-number field in a header/footer part and where it sits."""
    texts: list[str] = []
    found = False
    alignment = None
    fmt_switch = None
    for block in _iter_blocks(root, {"tables": []}):
        p_el = block.p_el
        style_id = resolver.paragraph_style_id(p_el)
        props = resolver.paragraph_props(resolver.ppr_layers(p_el, style_id, None))
        tracker = _FieldTracker()
        tabs_before = 0
        ptab = None
        text = ""
        for event, el in _walk_paragraph(p_el):
            if event == "simple_begin":
                tracker.begin(w_attr(el, "instr") or "")
            elif event == "simple_end":
                tracker.end()
            else:
                tracker.run(el)
                for child in el:
                    if child.tag == w("ptab"):
                        ptab = w_attr(child, "alignment")
                text += _run_text(el)
                if not found:
                    tabs_before = text.count("\t")
            for _, instr in tracker.open_fields() + tracker.finished:
                if not found and _PAGE_FIELD_RE.match(instr):
                    found = True
                    switch = _FORMAT_SWITCH_RE.search(instr)
                    fmt_switch = switch.group(1) if switch else None
                    alignment = _page_alignment(props, tabs_before, ptab)
        texts.append(text)
    return HeaderFooterView(
        kind=kind,
        text="\n".join(texts).strip(),
        has_page_field=found,
        page_alignment=alignment,
        page_format_switch=fmt_switch,
    )


def _page_alignment(props: dict[str, Any], tabs_before: int, ptab: str | None) -> str:
    """Where a page number appears: by alignment tab, by tab stops, or paragraph alignment."""
    if ptab in ("left", "center", "right"):
        return ptab
    if tabs_before and props["tabs"]:
        stops = props["tabs"]
        stop = stops[min(tabs_before, len(stops)) - 1][0]
        return {"center": "center", "right": "right", "end": "right"}.get(stop, "left")
    if tabs_before == 1:
        return "center"  # Word's Header/Footer styles centre the first tab stop
    return props["alignment"] if props["alignment"] != "justified" else "left"


def _section_view(
    index: int, sect_pr: Any, previous: SectionView | None, document: Any, resolver
) -> SectionView:
    pg_sz = sect_pr.find(w("pgSz"))
    pg_mar = sect_pr.find(w("pgMar"))
    pg_num = sect_pr.find(w("pgNumType"))
    start = w_attr(pg_num, "start")
    headers: dict[str, HeaderFooterView | None] = {}
    footers: dict[str, HeaderFooterView | None] = {}
    parts = (("header", headers, "headerReference"), ("footer", footers, "footerReference"))
    for kind, store, tag in parts:
        own = {w_attr(ref, "type") or "default": ref for ref in sect_pr.findall(w(tag))}
        for hf_type in ("default", "first", "even"):
            if hf_type in own:
                root = _part_root(document, own[hf_type].get(f"{{{R_NS}}}id"))
                store[hf_type] = None if root is None else _header_footer_view(root, kind, resolver)
            else:
                # No reference of this type = "Link to previous": reuse the last one.
                if previous is None:
                    store[hf_type] = None
                else:
                    inherited = previous.headers if kind == "header" else previous.footers
                    store[hf_type] = inherited.get(hf_type)
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
        title_page=_toggle(sect_pr.find(w("titlePg"))) or False,
        page_number_start=int(start) if start and start.isdigit() else None,
        page_number_format=w_attr(pg_num, "fmt"),
        break_type=w_attr(sect_pr.find(w("type")), "val") or "nextPage",
        headers=headers,
        footers=footers,
    )


def _has_image(p_el: Any) -> bool:
    for el in p_el.iter(f"{{{A_NS}}}blip", f"{{{V_NS}}}imagedata", f"{{{A_NS}}}graphicData"):
        if el.tag.endswith("graphicData"):
            uri = el.get("uri") or ""
            if "chart" in uri or "diagram" in uri:
                return True
            continue
        if not any(a.tag == f"{{{MC_NS}}}Fallback" for a in el.iterancestors()):
            return True
    return False


def _textbox_texts(p_el: Any) -> list[str]:
    texts = []
    for box in p_el.iter(w("txbxContent")):
        if any(a.tag == f"{{{MC_NS}}}Fallback" for a in box.iterancestors()):
            continue  # same text box again, in the legacy format
        for inner in box.iter(w("p")):
            text = "".join(_run_text(r) for kind, r in _walk_paragraph(inner) if kind == "run")
            if text.strip():
                texts.append(text)
    return texts


_LV_LETTERS = set("āčēģīķļņšūžĀČĒĢĪĶĻŅŠŪŽ")


def _paragraph_lang(runs: tuple[RunView, ...], text: str) -> str | None:
    """The language most of the paragraph's characters are marked with (w:lang),
    else a heuristic: Latvian letters (ā, č, …) mean Latvian."""
    counts: Counter[str] = Counter()
    for run in runs:
        if run.lang and run.text.strip():
            counts[run.lang.split("-")[0].lower()] += len(run.text.strip())
    if counts:
        return counts.most_common(1)[0][0]
    if not text.strip():
        return None
    return "lv" if any(ch in _LV_LETTERS for ch in text) else "en"


def _caption_regex(labels: Iterable[str]) -> re.Pattern[str]:
    roots = {re.escape(lbl.strip().rstrip(".").casefold()) for lbl in labels if lbl.strip()}
    roots |= set(_GENERIC_CAPTION_ROOTS)
    alternatives = "|".join(sorted(roots, key=len, reverse=True))
    return re.compile(
        rf"^\s*(?:(?:{alternatives})\w*\.?\s*\d+(?:\.\d+)*|\d+(?:\.\d+)*\.?\s*(?:{alternatives})\w*\.?)"
        r"(?:\W|$)",
        re.IGNORECASE,
    )


@dataclass(frozen=True)
class ViewSettings:
    """Profile settings that change how the view is built."""

    non_body_styles: tuple[str, ...] = ()
    caption_labels: tuple[str, ...] = ()


def _looks_like_caption(text: str, style_name: str | None, caption_re: re.Pattern[str]) -> bool:
    if re.search(r"caption|figure|table-(name|number)", style_name or "", re.IGNORECASE):
        return True
    clean = " ".join(text.split())
    if not caption_re.match(clean):
        return False
    # "Figure 3 shows that …" is a sentence that MENTIONS a figure, not a caption.
    return not (clean.endswith(".") and len(clean.split()) > 8)


def build_view(document: Any, settings: ViewSettings | None = None) -> DocumentView:
    """Build the DocumentView from a python-docx Document. Reads only; changes nothing.

    `settings.non_body_styles` comes from the profile (`text.non_body_styles`):
    paragraph style names the university deliberately formats differently from
    body text (e.g. RTU's "Code" style is Arial Narrow 11 pt).
    """
    settings = settings or ViewSettings()
    extra_non_body = {name.casefold() for name in settings.non_body_styles}
    caption_re = _caption_regex(settings.caption_labels)
    body = document.element.body
    resolver = StyleResolver(document.styles.element, _related_root(document, "theme"))
    numbering = NumberingResolver(_related_root(document, "numbering"))

    # Sections: every <w:sectPr> in the body, in order (but not the "old" copies kept
    # inside <w:sectPrChange> for tracked changes).
    sect_prs = [s for s in body.iter(w("sectPr")) if s.getparent().tag != w("sectPrChange")]
    sections: list[SectionView] = []
    for i, sect_pr in enumerate(sect_prs):
        previous = sections[-1] if sections else None
        sections.append(_section_view(i, sect_pr, previous, document, resolver))

    state: dict[str, Any] = {"tables": []}
    blocks = list(_iter_blocks(body, state))
    has_rendered_breaks = any(True for _ in body.iter(w("lastRenderedPageBreak")))
    tracker = _FieldTracker()

    paragraphs: list[ParagraphView] = []
    textboxes: list[tuple[int, str]] = []
    field_paragraphs: dict[int, list[int]] = {}
    field_instr: dict[int, str] = {}
    section_index = 0
    page = 1
    words_on_page = 0
    heading_stack: list[tuple[int, str]] = []
    seen_first_heading = False

    for index, block in enumerate(blocks):
        p_el = block.p_el
        style_id = resolver.paragraph_style_id(p_el)
        style_name = resolver.style_name(style_id)

        # --- runs and fields ---------------------------------------------------------
        runs_list: list[RunView] = []
        touched: dict[int, str] = dict(tracker.open_fields())
        page_breaks = 0
        starts_with_break = False
        for event, el in _walk_paragraph(p_el):
            if event == "simple_begin":
                tracker.begin(w_attr(el, "instr") or "")
                touched.update(tracker.open_fields())
                continue
            if event == "simple_end":
                tracker.end()
                continue
            tracker.run(el)
            touched.update(tracker.open_fields())
            text = _run_text(el)
            for br in el.findall(w("br")):
                if w_attr(br, "type") == "page":
                    page_breaks += 1
                    if not "".join(r.text for r in runs_list).strip():
                        starts_with_break = True
            runs_list.append(resolver.resolve_run(el, style_id, text))
        for field_id, instr in tracker.finished:
            touched[field_id] = instr
        tracker.finished.clear()
        for field_id, instr in touched.items():
            field_paragraphs.setdefault(field_id, []).append(index)
            field_instr[field_id] = instr or field_instr.get(field_id, "")

        runs = tuple(runs_list)
        text = "".join(r.text for r in runs)
        level = None if block.in_table else resolver.heading_level(p_el, style_id)

        # --- list numbering and heading numbers -----------------------------------------
        num_pr = resolver.num_pr(p_el, style_id)
        num_view = numbering.next_label(*num_pr) if num_pr else None
        num_ppr = None
        if num_pr:
            lvl = numbering.level(*num_pr)
            num_ppr = lvl.find(w("pPr")) if lvl is not None else None
        props = resolver.paragraph_props(resolver.ppr_layers(p_el, style_id, num_ppr))

        heading_number = heading_dot = heading_source = None
        if level is not None:
            typed = _TYPED_NUMBER_RE.match(text)
            if num_view is not None and num_view.num_fmt != "bullet":
                list_match = re.match(r"^\s*(\d+(?:\.\d+)*)(\.?)\s*$", num_view.label)
                if list_match:
                    heading_number, heading_dot = list_match.group(1), bool(list_match.group(2))
                    heading_source = "list"
            elif typed:
                heading_number, heading_dot = typed.group(1), bool(typed.group(2))
                heading_source = "typed"

        # --- page estimate -----------------------------------------------------------
        if has_rendered_breaks:
            # Word remembers where pages broke the last time it laid out the file.
            page += sum(1 for _ in p_el.iter(w("lastRenderedPageBreak")))
        else:
            explicit = page_breaks + int(props["page_break_before"])
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

        has_math = p_el.find(f".//{{{M_NS}}}oMath") is not None
        has_image = _has_image(p_el)
        in_toc = any(re.match(r"^\s*TOC\b", i, re.IGNORECASE) for i in touched.values())
        caption_like = (
            not block.in_table
            and level is None
            and _looks_like_caption(text, style_name, caption_re)
        )
        is_body = (
            seen_first_heading  # text before the first heading = title page (TITLE rules)
            and level is None
            and not block.in_table  # tables may legitimately use smaller text
            and bool(text.strip())
            and not has_math
            and not in_toc
            and not caption_like
            and not _NON_BODY_STYLE_RE.match(style_name or "")
            and (style_name or "").casefold() not in extra_non_body
        )
        for box_text in _textbox_texts(p_el):
            textboxes.append((index, box_text))

        sect_pr = p_el.find(f"{w('pPr')}/{w('sectPr')}")
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
                in_table=block.in_table,
                is_body=is_body,
                runs=runs,
                alignment=props["alignment"],
                line_rule=props["line_rule"],
                line_value=props["line_value"],
                space_before=props["space_before"],
                space_after=props["space_after"],
                indent_left=props["indent_left"],
                first_line=props["first_line"],
                tabs=props["tabs"],
                page_break_before=props["page_break_before"],
                starts_with_page_break=starts_with_break,
                has_page_break=page_breaks > 0,
                ends_section=sect_pr is not None,
                section_break_type=(
                    (w_attr(sect_pr.find(w("type")), "val") or "nextPage")
                    if sect_pr is not None
                    else None
                ),
                has_image=has_image,
                has_math=has_math,
                has_note_ref=p_el.find(f".//{w('footnoteReference')}") is not None
                or p_el.find(f".//{w('endnoteReference')}") is not None,
                numbering=num_view,
                heading_number=heading_number,
                heading_number_dot=bool(heading_dot),
                heading_number_source=heading_source,
                table_index=block.table_index,
                lang=_paragraph_lang(runs, text),
                fields=tuple(sorted(touched.items())),
                is_caption_like=caption_like,
            )
        )
        # A <w:sectPr> inside a paragraph's properties ENDS a section at that paragraph.
        if sect_pr is not None:
            section_index += 1

    settings_el = document.settings.element
    return DocumentView(
        paragraphs=tuple(paragraphs),
        sections=tuple(sections),
        mirror_margins=_toggle(settings_el.find(w("mirrorMargins"))) or False,
        theme_fonts=dict(resolver.theme_fonts),
        tables=_table_views(paragraphs),
        fields=tuple(
            FieldView(fid, field_instr[fid], tuple(dict.fromkeys(idx)))
            for fid, idx in sorted(field_paragraphs.items())
        ),
        footnotes=_footnote_texts(document),
        textboxes=tuple(textboxes),
        has_rendered_breaks=has_rendered_breaks,
        has_tracked_changes=any(
            True for _ in body.iter(w("ins"), w("del"), w("moveFrom"), w("moveTo"))
        ),
        update_fields_on_open=_toggle(settings_el.find(w("updateFields"))) or False,
        even_and_odd_headers=_toggle(settings_el.find(w("evenAndOddHeaders"))) or False,
    )


def _table_views(paragraphs: list[ParagraphView]) -> tuple[TableView, ...]:
    by_table: dict[int, list[int]] = {}
    for p in paragraphs:
        if p.table_index is not None:
            by_table.setdefault(p.table_index, []).append(p.index)
    tables = []
    for t_index, indices in sorted(by_table.items()):
        first, last = indices[0], indices[-1]
        tables.append(
            TableView(
                index=t_index,
                first_paragraph=first,
                last_paragraph=last,
                before_paragraph=first - 1 if first > 0 else None,
                after_paragraph=last + 1 if last + 1 < len(paragraphs) else None,
            )
        )
    return tuple(tables)


def _footnote_texts(document: Any) -> tuple[str, ...]:
    texts: list[str] = []
    for part_name in ("footnotes", "endnotes"):
        root = _related_root(document, part_name)
        if root is None:
            continue
        for note in root:
            if w_attr(note, "type") in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            for p_el in note.iter(w("p")):
                text = "".join(_run_text(r) for kind, r in _walk_paragraph(p_el) if kind == "run")
                if text.strip():
                    texts.append(text)
    return tuple(texts)
