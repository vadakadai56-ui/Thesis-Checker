"""Plain data objects shared by every part of the engine (BUILD_PROMPT §6).

Only the Python standard library is used here, so this file works the same in
pytest and inside Pyodide in the browser. Every object that leaves the engine has
a `version` field so the app can notice if the format ever changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]
SEVERITIES: tuple[Severity, ...] = ("error", "warning", "info")

FINDING_VERSION = 1
REPORT_VERSION = 1

# A profile value of exactly this string means "waiting for the faculty guideline".
TODO = "TODO"


def contains_todo(value: Any) -> bool:
    """True if `value` is "TODO" or contains "TODO" anywhere inside lists/dicts."""
    if isinstance(value, str):
        return value == TODO
    if isinstance(value, dict):
        return any(contains_todo(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_todo(v) for v in value)
    return False


# --------------------------------------------------------------------------- errors

# Friendly messages from BUILD_PROMPT §9. The UI shows `message`; `detail` is for us.
ERROR_MESSAGES: dict[str, str] = {
    "FILE_TOO_LARGE": "This file is too big to check (the limit is 50 MB).",
    "NOT_DOCX": "This doesn't look like a Word .docx file.",
    "LEGACY_DOC": "This is an old .doc file. Open it in Word or LibreOffice and save as .docx.",
    "ODT": "This is an OpenDocument file. In LibreOffice choose File → Save As → Word (.docx).",
    "ENCRYPTED": (
        "This file is password-protected. Remove the password in Word "
        "(File → Info → Protect Document), save, and try again."
    ),
    "MACRO_DOCM": "Files with macros aren't accepted, for your safety. Save as a normal .docx.",
    "CORRUPT": (
        "This file looks damaged. Open it in Word, use File → Save As .docx, and try again."
    ),
    "ZIP_BOMB": (
        "This file looks damaged. Open it in Word, use File → Save As .docx, and try again."
    ),
    "INTERNAL": "Something went wrong inside ThesisCheck. Please try again.",
}


class EngineError(Exception):
    """An expected problem with the input file, carrying a code from BUILD_PROMPT §6d."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.message = ERROR_MESSAGES.get(code, ERROR_MESSAGES["INTERNAL"])
        self.detail = detail
        super().__init__(f"{code}: {detail or self.message}")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


# ------------------------------------------------------------------------- findings


@dataclass(frozen=True)
class Location:
    """Where a problem is. Page numbers are estimates: only Word knows real pages."""

    part: str = "body"  # body | header | footer | footnotes | settings | styles
    paragraph_index: int | None = None
    section_index: int | None = None
    page_estimate: int | None = None
    heading_path: tuple[str, ...] = ()
    snippet: str = ""


@dataclass
class Finding:
    id: str
    rule_id: str
    category: str
    severity: Severity
    message: str
    rule_text: str
    guideline_ref: str
    location: Location
    expected: Any
    found: Any
    fixable: bool
    fixed: bool = False
    how_to_fix: str = ""
    version: int = FINDING_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["location"]["heading_path"] = list(self.location.heading_path)
        return d


@dataclass(frozen=True)
class SkippedRule:
    rule_id: str
    reason: str


# ------------------------------------------------------------------------- profiles


@dataclass(frozen=True)
class RuleConfig:
    """One rule's settings, copied from the profile."""

    rule_id: str
    severity: Severity
    autofix: bool
    rule_text: str
    guideline_ref: str
    expected: Any = None
    blocking: bool = False

    @property
    def pending(self) -> bool:
        """A rule whose value or source is still TODO is not checked yet."""
        return contains_todo(self.expected) or self.guideline_ref == TODO


@dataclass(frozen=True)
class Profile:
    id: str
    version: int
    status: str  # draft | verified
    name: str
    rules: dict[str, RuleConfig]
    # Everything else from the profile (structure, captions, checklist, …) as plain data.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Report:
    engine_version: str
    document_sha256: str
    file_name: str
    profile: dict[str, Any]
    created_at: str
    stats: dict[str, int]
    findings: list[Finding]
    score: dict[str, Any]  # see scoring.py
    skipped_rules: list[SkippedRule]
    version: int = REPORT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "engine_version": self.engine_version,
            "document_sha256": self.document_sha256,
            "file_name": self.file_name,
            "profile": self.profile,
            "created_at": self.created_at,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
            "score": self.score,
            "skipped_rules": [asdict(s) for s in self.skipped_rules],
        }
