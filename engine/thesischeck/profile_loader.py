"""Turn a compiled profile (JSON) into Profile/RuleConfig objects.

The YAML profiles are validated thoroughly with Pydantic at build time
(engine/tools/compile_profiles.py). Pydantic and PyYAML are NOT shipped to the
browser, so here we only do light sanity checks with the standard library.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import SEVERITIES, Profile, RuleConfig

SUPPORTED_PROFILE_VERSION = 1


def load_profile(data: dict[str, Any]) -> Profile:
    if data.get("version") != SUPPORTED_PROFILE_VERSION:
        raise ValueError(f"unsupported profile version: {data.get('version')!r}")

    rules: dict[str, RuleConfig] = {}
    for rule_id, cfg in (data.get("rules") or {}).items():
        severity = cfg["severity"]
        if severity not in SEVERITIES:
            raise ValueError(f"{rule_id}: bad severity {severity!r}")
        rules[rule_id] = RuleConfig(
            rule_id=rule_id,
            severity=severity,
            autofix=bool(cfg.get("autofix", False)),
            rule_text=cfg["rule_text"],
            guideline_ref=cfg["guideline_ref"],
            expected=cfg.get("expected"),
            blocking=bool(cfg.get("blocking", False)),
        )

    known = {"version", "id", "status", "name", "rules"}
    return Profile(
        id=data["id"],
        version=data["version"],
        status=data["status"],
        name=data.get("name", data["id"]),
        rules=rules,
        extra={k: v for k, v in data.items() if k not in known},
    )


def load_profile_file(path: str | Path) -> Profile:
    return load_profile(json.loads(Path(path).read_text(encoding="utf-8")))
