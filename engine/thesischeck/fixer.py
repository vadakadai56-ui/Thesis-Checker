"""Auto-fix (BUILD_PROMPT §4d) — the ONLY module (with annotator.py) that writes.

    fix(bytes, profile) -> {"bytes": NEW .docx, "report": re-check, "fixes": […], …}

1. Check the original (to know what's wrong).
2. Open an independent COPY of the bytes — the input is never modified.
3. Run the fix function of every rule that has fixable findings.
4. Save the copy to new bytes and check it again.
5. Safety net: the words of the fixed copy must equal the original's (only empty
   paragraphs may disappear). If not, refuse rather than hand back changed text.

Fixes are formatting-only: they change styles, paragraph settings, page setup,
headers/footers and document settings — never a word of the student's text.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePath
from typing import Any

from .api import _as_profile, check, view_settings
from .document_view import (
    DocumentView,
    ParagraphView,
    StyleResolver,
    _iter_blocks,
    _related_root,
    _walk_paragraph,
    build_view,
)
from .docx_io import open_docx
from .model import EngineError, Finding, Profile, RuleConfig
from .profile_loader import load_profile
from .regions import Regions
from .rule_ids import ALL_RULE_IDS
from .rules.registry import get_fixer, get_rule

FIX_RESULT_VERSION = 1


@dataclass
class FixContext:
    """What a fix function gets: the COPY to change, plus the original's view."""

    document: Any  # python-docx Document (the copy)
    view: DocumentView  # read-only view of the document BEFORE any fix
    paragraphs: list[Any]  # <w:p> elements of the copy, in the same order as view.paragraphs
    regions: Regions
    profile: Profile
    cfg: RuleConfig
    findings: list[dict[str, Any]]  # this rule's fixable findings (report dicts)
    _resolver: StyleResolver | None = field(default=None, repr=False)

    @property
    def expected(self) -> Any:
        return self.cfg.expected if self.cfg.expected is not None else {}

    @property
    def resolver(self) -> StyleResolver:
        """Resolves formatting on the COPY (sees style changes made by earlier fixes)."""
        if self._resolver is None:
            self._resolver = StyleResolver(
                self.document.styles.element, _related_root(self.document, "theme")
            )
        return self._resolver

    def element(self, index: int) -> Any:
        return self.paragraphs[index]

    def runs(self, index: int) -> list[Any]:
        """The <w:r> elements of paragraph `index`, in the same order as the view's runs."""
        return [el for kind, el in _walk_paragraph(self.paragraphs[index]) if kind == "run"]

    def finding_paragraphs(self) -> list[ParagraphView]:
        indices = {
            f["location"]["paragraph_index"]
            for f in self.findings
            if f["location"]["paragraph_index"] is not None
        }
        return [self.view.paragraphs[i] for i in sorted(indices)]

    def finding_sections(self) -> list[int]:
        return sorted(
            {
                f["location"]["section_index"]
                for f in self.findings
                if f["location"]["section_index"] is not None
            }
        )

    def sect_pr(self, section_index: int) -> Any:
        return self.document.sections[section_index]._sectPr

    def style_element(self, style_id: str | None) -> Any | None:
        """The <w:style> element for a style ID in the copy (None for no style)."""
        return self.resolver.styles.get(style_id or "")


def _words(view: DocumentView) -> list[str]:
    """Every word of the document's body text, in order (for the safety net)."""
    return [word for p in view.paragraphs for word in p.text.split()]


def _fixed_name(file_name: str, suffix: str) -> str:
    path = PurePath(file_name or "document.docx")
    return f"{path.stem}_{suffix}.docx"


def apply_fixes(
    data: bytes, profile: Profile, before: dict[str, Any]
) -> tuple[Any, DocumentView, list[dict[str, Any]]]:
    """Open a copy of `data`, apply every applicable fix. Returns (document, view, summary)."""
    document = open_docx(data)  # an independent copy: `data` itself is never touched
    view = build_view(document, view_settings(profile))
    paragraphs = [block.p_el for block in _iter_blocks(document.element.body, {"tables": []})]
    regions = Regions(view, profile.extra.get("structure"))

    by_rule: dict[str, list[dict[str, Any]]] = {}
    for finding in before["findings"]:
        if finding["fixable"]:
            by_rule.setdefault(finding["rule_id"], []).append(finding)

    summary: list[dict[str, Any]] = []
    for rule_id in ALL_RULE_IDS:  # fixed order = same result every time
        fix_fn: Callable[[FixContext], int] | None = get_fixer(rule_id)
        if rule_id not in by_rule or fix_fn is None:
            continue
        ctx = FixContext(
            document=document,
            view=view,
            paragraphs=paragraphs,
            regions=regions,
            profile=profile,
            cfg=profile.rules[rule_id],
            findings=by_rule[rule_id],
        )
        changes = fix_fn(ctx)
        spec = get_rule(rule_id)
        summary.append(
            {
                "rule_id": rule_id,
                "title": spec.title if spec else rule_id,
                "findings": len(by_rule[rule_id]),
                "changes": changes,
            }
        )
    return document, view, summary


def _save(document: Any) -> bytes:
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def fix(
    data: bytes,
    profile: Profile | dict[str, Any],
    file_name: str = "document.docx",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a NEW, fixed .docx plus its report. `data` is never modified."""
    prof = _as_profile(profile)
    before = check(data, prof, file_name=file_name, now=now)
    document, original_view, summary = apply_fixes(data, prof, before)
    fixed_bytes = _save(document)

    fixed_name = _fixed_name(file_name, "fixed")
    after = check(fixed_bytes, prof, file_name=fixed_name, now=now)
    fixed_view = build_view(open_docx(fixed_bytes), view_settings(prof))
    if _words(fixed_view) != _words(original_view):
        # Should never happen; refusing is better than changing a student's text.
        raise EngineError("INTERNAL", "auto-fix would have changed the text; nothing was saved")

    _mark_fixed(before, after)
    return {
        "version": FIX_RESULT_VERSION,
        "kind": "fixed",
        "file_name": fixed_name,
        "bytes": fixed_bytes,
        "report": after,
        "before": {"score": before["score"], "findings": len(before["findings"])},
        "fixed_findings": [f for f in before["findings"] if f["fixed"]],
        "fixes": summary,
    }


def _key(f: dict[str, Any]) -> tuple:
    # Not the paragraph number: removing empty paragraphs shifts those. The snippet
    # (the text) never changes, because fixes never change text.
    loc = f["location"]
    return (f["rule_id"], loc["snippet"], loc["section_index"], loc["part"], str(f["found"]))


def _mark_fixed(before: dict[str, Any], after: dict[str, Any]) -> None:
    """A finding is 'fixed' if it was fixable and is gone after the fix."""
    remaining = {_key(f) for f in after["findings"]}
    for finding in before["findings"]:
        finding["fixed"] = bool(finding["fixable"]) and _key(finding) not in remaining


__all__ = ["Finding", "FixContext", "fix", "load_profile"]

# Registers the fix functions. At the bottom, because they import FixContext above.
from . import fixes  # noqa: E402, F401
