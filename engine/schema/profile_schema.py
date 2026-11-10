"""Pydantic models that validate a profile YAML (BUILD_PROMPT §6a).

Used only at build/test time (compile_profiles.py, pytest) — never in the browser.

Main checks:
* every rule ID exists (typos are caught),
* severities, levels, statuses are from the allowed lists,
* rules with a known `expected` shape have the right fields (e.g. PAGE-01 needs
  top_cm/bottom_cm/left_cm/right_cm),
* the value "TODO" is only allowed while `status: draft`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    TypeAdapter,
    model_validator,
)

# Allow `from thesischeck…` when this file is used from engine/tools or engine/tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from thesischeck.model import TODO, contains_todo
from thesischeck.rule_ids import ALL_RULE_IDS


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------- per-rule `expected` shapes


class MarginsExpected(_Strict):
    top_cm: PositiveFloat
    bottom_cm: PositiveFloat
    left_cm: PositiveFloat
    right_cm: PositiveFloat
    tolerance_cm: PositiveFloat = 0.05


class PaperExpected(_Strict):
    paper: Literal["A4", "Letter"]


class OrientationExpected(_Strict):
    landscape: Literal["never", "appendices_only", "allowed"]


class GutterExpected(_Strict):
    gutter_cm: NonNegativeFloat = 0
    mirror_margins: bool = False


class FontExpected(_Strict):
    font: str = Field(min_length=1)


class FontSizeExpected(_Strict):
    size_pt: PositiveFloat


class LineSpacingExpected(_Strict):
    line_spacing: PositiveFloat  # in lines: 1.5 = one and a half lines


class AlignmentExpected(_Strict):
    alignment: Literal["justified", "left", "center", "right"]


class SpacingExpected(_Strict):
    before_pt: NonNegativeFloat = 0
    after_pt: NonNegativeFloat = 0
    tolerance_pt: NonNegativeFloat = 0.5


class IndentExpected(_Strict):
    first_line_cm: float
    tolerance_cm: PositiveFloat = 0.05


class DirectFormattingExpected(_Strict):
    max_percent: float = Field(50, ge=0, le=100)


class EmptyParagraphsExpected(_Strict):
    max_consecutive_empty: NonNegativeInt = 1


class FakeHeadingExpected(_Strict):
    max_words: int = Field(12, ge=1)


class HeadingStyle(_Strict):
    font: str | None = None
    size_pt: PositiveFloat | None = None
    bold: bool | None = None
    caps: bool | None = None
    align: Literal["left", "center", "right", "justified"] | None = None
    before_pt: NonNegativeFloat | None = None
    after_pt: NonNegativeFloat | None = None


class NumberingExpected(_Strict):
    format: list[str]  # per level, e.g. ["1.", "1.1.", "1.1.1."]
    unnumbered: list[str] = []


class NewPageExpected(_Strict):
    new_page: bool = True


class PageNumberExpected(_Strict):
    position: Literal[
        "bottom_center", "bottom_right", "bottom_left", "top_center", "top_right", "top_left"
    ]
    format: Literal["arabic", "roman"] = "arabic"


class TitlePageNumberExpected(_Strict):
    title_page_shows_number: bool = False
    title_page_counted: bool | None = None


class AbstractExpected(_Strict):
    sections: list[str] = ["abstract"]
    max_pages: PositiveFloat | None = None
    max_words: int | None = None
    keywords_min: int | None = None
    keywords_max: int | None = None


class Limits(_Strict):
    min_pages: NonNegativeFloat | None = None
    max_pages: PositiveFloat | None = None
    min_words: NonNegativeInt | None = None
    max_words: NonNegativeInt | None = None


class LengthExpected(_Strict):
    sections: dict[str, Limits] = {}
    main_text: Limits | None = None


class ListRequiredExpected(_Strict):
    required: bool = False


class CitationStyleExpected(_Strict):
    style: Literal["author-date", "numeric"]


class MinWordsExpected(_Strict):
    min_words: int = Field(ge=1)


class EntryExpected(_Strict):
    access_date_required: bool = True
    doi_exempt: bool = True


class OrderExpected(_Strict):
    order: Literal["alphabetical", "citation"]


class RefFormatExpected(_Strict):
    hanging_indent_cm: NonNegativeFloat | None = None
    line_spacing: PositiveFloat | None = None
    before_pt: NonNegativeFloat | None = None
    after_pt: NonNegativeFloat | None = None


class AbbreviationExpected(_Strict):
    allow: list[str] = []


HeadingLevels = dict[int, HeadingStyle]
CapsLevels = dict[int, Literal["all_caps", "sentence_case", "as_typed"]]

# `expected` shape per rule. None = the rule takes no expected value (it reads other
# profile sections, e.g. `structure` or `captions`, or needs no settings).
EXPECTED_MODELS: dict[str, Any] = {
    "PAGE-01": MarginsExpected,
    "PAGE-02": PaperExpected,
    "PAGE-03": OrientationExpected,
    "PAGE-04": GutterExpected,
    "TEXT-01": FontExpected,
    "TEXT-02": FontSizeExpected,
    "TEXT-03": LineSpacingExpected,
    "TEXT-04": AlignmentExpected,
    "TEXT-05": SpacingExpected,
    "TEXT-06": IndentExpected,
    "TEXT-07": DirectFormattingExpected,
    "TEXT-08": EmptyParagraphsExpected,
    "HEAD-01": FakeHeadingExpected | None,
    "HEAD-02": HeadingLevels,
    "HEAD-03": None,
    "HEAD-04": NumberingExpected,
    "HEAD-05": CapsLevels,
    "HEAD-06": NewPageExpected,
    "PGNUM-01": None,
    "PGNUM-02": PageNumberExpected,
    "PGNUM-03": TitlePageNumberExpected,
    "STRUCT-01": None,
    "STRUCT-02": None,
    "STRUCT-03": AbstractExpected,
    "STRUCT-04": LengthExpected,
    "STRUCT-05": None,
    "TOC-01": None,
    "TOC-02": None,
    "TOC-03": None,
    "FIG-01": None,
    "FIG-02": None,
    "FIG-03": None,
    "FIG-04": None,
    "TAB-01": None,
    "TAB-02": None,
    "TAB-03": None,
    "TAB-04": None,
    "LIST-01": ListRequiredExpected | None,
    "CITE-01": None,
    "CITE-02": None,
    "CITE-03": CitationStyleExpected,
    "CITE-04": MinWordsExpected,
    "CITE-05": MinWordsExpected,
    "REF-01": EntryExpected | None,
    "REF-02": OrderExpected,
    "REF-03": RefFormatExpected,
    "REF-04": None,
    "REF-AI-01": None,
    "CONS-01": None,
    "CONS-02": AbbreviationExpected | None,
    "CONS-03": None,
    "TITLE-01": None,
    "TITLE-02": None,
}


class RuleEntry(_Strict):
    severity: Literal["error", "warning", "info"]
    autofix: bool = False
    rule_text: str = Field(min_length=1)
    guideline_ref: str = Field(min_length=1)
    expected: Any = None
    blocking: bool = False


class TextSettings(_Strict):
    # Paragraph style names (case-insensitive) that are NOT body text, because the
    # university formats them differently on purpose.
    non_body_styles: list[str] = []


class SectionDef(_Strict):
    """How to recognise one part of the thesis."""

    label: str | None = None
    headings: list[str] = []  # whole-heading texts, any language/case
    starts_with: list[str] = []  # or: its first paragraph starts like this


class OptionalPart(_Strict):
    name: str
    after: str  # which part it follows when present


BUILT_IN_PARTS = {"title_page", "chapters"}


class StructureSettings(_Strict):
    sections: dict[str, SectionDef] = {}
    required_order: list[str] = []
    optional: list[OptionalPart] = []
    keyword_labels: list[str] = []
    literature_review_headings: list[str] | Literal["TODO"] = []

    @model_validator(mode="after")
    def _known_parts(self) -> StructureSettings:
        known = set(self.sections) | BUILT_IN_PARTS
        names = list(self.required_order) + [o.name for o in self.optional]
        unknown = sorted(set(names) - known)
        if unknown:
            raise ValueError(f"structure: parts not defined in `sections`: {unknown}")
        return self


class CaptionDef(_Strict):
    label: str
    per_chapter: bool = True
    position: Literal["above", "below"]
    pattern: str | None = None  # for people reading the profile; not used by code
    align: str | None = None
    bold: bool | None = None
    style: str | None = None
    name_style: str | None = None


class TitleField(_Strict):
    id: str
    label: str
    patterns: list[str] = []  # regular expressions; empty = can't be checked automatically


class TitlePageSettings(_Strict):
    fields: list[TitleField] = []


class Source(_Strict):
    id: str
    title: str
    file: str


class ProfileModel(_Strict):
    version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    status: Literal["draft", "verified"]
    name: str
    short_name: str | None = None  # used in comments: "RTU rule: …"
    demo: bool = False
    university: str
    faculty: str | None = None
    programme: str | None = None
    degree_level: Literal["bachelor", "master", "any"]
    languages: list[str]
    citation_style: Literal["author-date", "numeric"] | Literal["TODO"]
    date_format: str
    sources: list[Source] = []
    rules: dict[str, RuleEntry]
    text: TextSettings = TextSettings()
    structure: StructureSettings = StructureSettings()
    captions: dict[str, CaptionDef | Literal["TODO"]] = {}
    title_page: TitlePageSettings = TitlePageSettings()
    ai_disclosure: dict[str, Any] = {}
    manual_checklist: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> ProfileModel:
        unknown = sorted(set(self.rules) - set(ALL_RULE_IDS))
        if unknown:
            raise ValueError(f"unknown rule IDs: {unknown}")

        for rule_id, entry in self.rules.items():
            if contains_todo(entry.expected):
                continue
            shape = EXPECTED_MODELS[rule_id]
            if shape is None:
                if entry.expected is not None:
                    raise ValueError(f"{rule_id}: takes no `expected` value")
                continue
            try:
                adapter = TypeAdapter(shape)
                # No value = use the defaults (fails if the rule has required settings).
                value = entry.expected if entry.expected is not None else {}
                entry.expected = adapter.dump_python(
                    adapter.validate_python(value), exclude_none=True
                )
            except ValueError as exc:
                raise ValueError(f"{rule_id}: bad `expected`: {exc}") from exc

        if self.status == "verified" and contains_todo(self.model_dump()):
            raise ValueError(f"profile is 'verified' but still contains {TODO!r} values")

        source_ids = {s.id for s in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("duplicate source IDs")
        refs = {r.guideline_ref.split(":")[0].split(" ")[0] for r in self.rules.values()}
        for ref in refs:
            looks_like_source = ref.endswith("-slides") or ref.startswith("rtu-template")
            if looks_like_source and ref not in source_ids:
                raise ValueError(f"guideline_ref names unknown source {ref!r}")
        return self
