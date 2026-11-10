"""Entry points used by BOTH pytest/the CLI and (from stage 4) the browser worker.

Inputs and outputs are plain bytes / dicts so they cross the Python ↔ JavaScript
boundary easily. The input bytes are never modified.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from .checker import run_checks
from .document_view import build_view
from .docx_io import open_docx
from .model import Profile, Report
from .profile_loader import load_profile

ENGINE_VERSION = "0.1.0"


def _as_profile(profile: Profile | dict[str, Any]) -> Profile:
    return profile if isinstance(profile, Profile) else load_profile(profile)


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
    non_body = prof.extra.get("text", {}).get("non_body_styles", [])
    view = build_view(document, non_body)
    findings, skipped = run_checks(view, prof)

    report = Report(
        engine_version=ENGINE_VERSION,
        document_sha256=sha256,
        file_name=file_name,
        profile={"id": prof.id, "version": prof.version, "status": prof.status},
        created_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
        stats=view.stats,
        findings=findings,
        score=None,  # stage 2
        skipped_rules=skipped,
    )
    return report.to_dict()


def fix(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("Auto-fix arrives in stage 3.")


def annotate(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("The annotated copy arrives in stage 3.")


def score(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError("The readiness score arrives in stage 2.")
