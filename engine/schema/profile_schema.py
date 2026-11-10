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

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, model_validator

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


class FontExpected(_Strict):
    font: str = Field(min_length=1)


class FontSizeExpected(_Strict):
    size_pt: PositiveFloat


# Rules not listed here accept any `expected` value for now; each later stage adds
# a shape here when it implements the rule.
EXPECTED_MODELS: dict[str, type[BaseModel] | None] = {
    "PAGE-01": MarginsExpected,
    "PAGE-02": PaperExpected,
    "TEXT-01": FontExpected,
    "TEXT-02": FontSizeExpected,
    "HEAD-03": None,  # needs no expected value
}


class RuleEntry(_Strict):
    severity: Literal["error", "warning", "info"]
    autofix: bool = False
    rule_text: str = Field(min_length=1)
    guideline_ref: str = Field(min_length=1)
    expected: Any = None
    blocking: bool = False


class Source(_Strict):
    id: str
    title: str
    file: str


class ProfileModel(_Strict):
    version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    status: Literal["draft", "verified"]
    name: str
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
    structure: dict[str, Any] = {}
    captions: dict[str, Any] = {}
    ai_disclosure: dict[str, Any] = {}
    manual_checklist: list[str] = []

    @model_validator(mode="after")
    def _check(self) -> ProfileModel:
        unknown = sorted(set(self.rules) - set(ALL_RULE_IDS))
        if unknown:
            raise ValueError(f"unknown rule IDs: {unknown}")

        for rule_id, entry in self.rules.items():
            if rule_id not in EXPECTED_MODELS or contains_todo(entry.expected):
                continue
            model = EXPECTED_MODELS[rule_id]
            if model is None:
                if entry.expected is not None:
                    raise ValueError(f"{rule_id}: takes no `expected` value")
            else:
                entry.expected = model.model_validate(entry.expected).model_dump()

        if self.status == "verified" and contains_todo(self.model_dump()):
            raise ValueError(f"profile is 'verified' but still contains {TODO!r} values")

        source_ids = {s.id for s in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("duplicate source IDs")
        return self
