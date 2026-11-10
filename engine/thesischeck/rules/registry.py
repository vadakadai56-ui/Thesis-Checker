"""The rule registry: one place that maps a rule ID to its check function.

How to write a rule (see also the future `thesischeck-new-rule` skill):

    @rule("PAGE-02", title="Paper size", how_to_fix="Layout → Size → A4.")
    def check_paper_size(ctx: RuleContext) -> None:
        ...
        ctx.report(message=..., location=..., expected=..., found=...)

* A check function only READS `ctx.view` (a frozen DocumentView). It never changes
  the document — only fixer.py / annotator.py write, and only on a copy.
* Expected values come from `ctx.cfg.expected` (the profile), never hard-coded.
* If a rule cannot run on this document (e.g. no headings at all), raise
  `SkipRule("reason")` instead of reporting false errors.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..document_view import DocumentView, ParagraphView, SectionView
from ..model import Finding, Location, Profile, RuleConfig
from ..regions import Regions
from ..rule_ids import RULE_CATEGORIES


class SkipRule(Exception):
    """Raised by a check function when the rule doesn't apply to this document."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    category: str
    title: str
    how_to_fix: str
    check: Callable[[RuleContext], None]

    @property
    def can_fix(self) -> bool:
        """True if a fix function is registered for this rule (see thesischeck/fixes/)."""
        return self.rule_id in _FIXERS


@dataclass
class RuleContext:
    """Everything a check function needs, plus `report()` to record a problem."""

    view: DocumentView
    cfg: RuleConfig
    spec: RuleSpec
    regions: Regions
    profile: Profile
    today: date
    findings: list[Finding] = field(default_factory=list)

    @property
    def expected(self) -> Any:
        """The profile's expected value for this rule ({} if it has none)."""
        return self.cfg.expected if self.cfg.expected is not None else {}

    def body_paragraphs(self) -> list[ParagraphView]:
        """Body text, minus the table of contents (hand-typed contents lines)."""
        return [p for p in self.view.body_paragraphs if not self.regions.contains("toc", p.index)]

    def setting(self, *path: str, default: Any = None) -> Any:
        """A value from the profile's other sections, e.g. setting("captions", "figure")."""
        value: Any = self.profile.extra
        for key in path:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    def report(
        self,
        *,
        message: str,
        location: Location,
        expected: object,
        found: object,
        fixable: bool | None = None,
    ) -> None:
        """Record one problem. `fixable=False` marks a case the fixer can't handle."""
        can_fix = self.cfg.autofix and self.spec.can_fix and fixable is not False
        self.findings.append(
            Finding(
                id="",  # numbered by the checker once all rules have run
                rule_id=self.spec.rule_id,
                category=self.spec.category,
                severity=self.cfg.severity,
                message=message,
                rule_text=self.cfg.rule_text,
                guideline_ref=self.cfg.guideline_ref,
                location=location,
                expected=expected,
                found=found,
                fixable=can_fix,
                how_to_fix=self.spec.how_to_fix,
            )
        )


_REGISTRY: dict[str, RuleSpec] = {}
# Fix functions, kept apart from the (read-only) check functions. They are only ever
# called by fixer.py, on a COPY of the document.
_FIXERS: dict[str, Callable[..., int]] = {}


def rule(rule_id: str, *, title: str, how_to_fix: str):
    """Decorator that registers a check function under `rule_id`."""
    if rule_id not in RULE_CATEGORIES:
        raise ValueError(f"unknown rule ID {rule_id!r} (add it to rule_ids.py first)")

    def decorator(fn: Callable[[RuleContext], None]) -> Callable[[RuleContext], None]:
        if rule_id in _REGISTRY:
            raise ValueError(f"rule {rule_id} registered twice")
        _REGISTRY[rule_id] = RuleSpec(
            rule_id=rule_id,
            category=RULE_CATEGORIES[rule_id],
            title=title,
            how_to_fix=how_to_fix,
            check=fn,
        )
        return fn

    return decorator


def fixer(rule_id: str):
    """Decorator that registers a fix function for `rule_id`.

    A fix function receives a FixContext (see fixer.py) and returns how many
    changes it made. It may change formatting only — never the words.
    """
    if rule_id not in RULE_CATEGORIES:
        raise ValueError(f"unknown rule ID {rule_id!r}")

    def decorator(fn: Callable[..., int]) -> Callable[..., int]:
        if rule_id in _FIXERS:
            raise ValueError(f"fix for {rule_id} registered twice")
        _FIXERS[rule_id] = fn
        return fn

    return decorator


def get_fixer(rule_id: str) -> Callable[..., int] | None:
    return _FIXERS.get(rule_id)


def get_rule(rule_id: str) -> RuleSpec | None:
    return _REGISTRY.get(rule_id)


def registered_rule_ids() -> list[str]:
    return sorted(_REGISTRY)


# ------------------------------------------------------- location helpers for rules


def paragraph_location(p: ParagraphView) -> Location:
    return Location(
        part="body",
        paragraph_index=p.index,
        section_index=p.section_index,
        page_estimate=p.page_estimate,
        heading_path=p.heading_path,
        snippet=p.snippet,
    )


def settings_location() -> Location:
    return Location(part="settings")


def part_location(part: str) -> Location:
    return Location(part=part)


def section_location(view: DocumentView, section: SectionView) -> Location:
    """A section has no text of its own, so point at its first paragraph."""
    first = view.first_paragraph_of_section(section.index)
    if first is None:
        return Location(part="body", section_index=section.index)
    return Location(
        part="body",
        paragraph_index=first.index,
        section_index=section.index,
        page_estimate=first.page_estimate,
        heading_path=first.heading_path,
        snippet=first.snippet,
    )
