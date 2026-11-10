"""Entry points used by BOTH pytest/the CLI and (from stage 4) the browser worker.

Inputs and outputs are plain bytes / dicts so they cross the Python ↔ JavaScript
boundary easily. The input bytes are never modified.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from .checker import run_checks
from .document_view import ViewSettings, build_view
from .docx_io import open_docx
from .model import Profile, Report
from .profile_loader import load_profile
from .scoring import score as compute_score

ENGINE_VERSION = "0.1.0"


def _as_profile(profile: Profile | dict[str, Any]) -> Profile:
    return profile if isinstance(profile, Profile) else load_profile(profile)


def view_settings(profile: Profile) -> ViewSettings:
    """The profile values that change how the document is read (see ViewSettings)."""
    captions = profile.extra.get("captions") or {}
    labels = [c.get("label", "") for c in captions.values() if isinstance(c, dict)]
    return ViewSettings(
        non_body_styles=tuple((profile.extra.get("text") or {}).get("non_body_styles", [])),
        caption_labels=tuple(lbl for lbl in labels if lbl),
    )


def check(
    data: bytes,
    profile: Profile | dict[str, Any],
    file_name: str = "document.docx",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Check a .docx and return the report as a JSON-ready dict (BUILD_PROMPT §6c).

    Raises model.EngineError for files we refuse (damaged, macros, too big, …).
    `now` lets tests use a fixed timestamp.
    """
    prof = _as_profile(profile)
    sha256 = hashlib.sha256(data).hexdigest()
    document = open_docx(data)
    view = build_view(document, view_settings(prof))
    moment = now or datetime.now(UTC)
    findings, skipped = run_checks(view, prof, today=moment.date())

    report = Report(
        engine_version=ENGINE_VERSION,
        document_sha256=sha256,
        file_name=file_name,
        profile={"id": prof.id, "version": prof.version, "status": prof.status},
        created_at=moment.isoformat(timespec="seconds"),
        stats=view.stats,
        findings=findings,
        score=compute_score(findings, {rid for rid, cfg in prof.rules.items() if cfg.blocking}),
        skipped_rules=skipped,
    )
    return report.to_dict()


def fix(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("Auto-fix arrives in stage 3.")


def annotate(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("The annotated copy arrives in stage 3.")


def score(report: dict[str, Any]) -> dict[str, Any]:
    """The score of an existing report (e.g. to recompute after fixes are marked)."""
    return report["score"]
