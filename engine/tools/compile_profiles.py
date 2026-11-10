"""Compile profile YAML files into validated JSON for the app.

    python tools/compile_profiles.py            (run from engine/)

Reads   engine/profiles/*.yaml
Writes  public/profiles/<id>.json  and  public/profiles/index.json

YAML is the human-edited source of truth. The app (and the engine in the browser)
only reads the compiled JSON, so Pydantic and PyYAML never ship to users.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from schema.profile_schema import ProfileModel  # noqa: E402

PROFILES_DIR = ENGINE_DIR / "profiles"
OUTPUT_DIR = ENGINE_DIR.parent / "public" / "profiles"


def compile_profile_data(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate one profile (already loaded from YAML) and return the JSON-ready dict."""
    model = ProfileModel.model_validate(raw)
    # exclude_none keeps the JSON small; field order follows the schema.
    return model.model_dump(mode="json", exclude_none=True)


def compile_profile_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)  # safe_load: never runs code from the YAML
    compiled = compile_profile_data(raw)
    if f"{compiled['id']}.yaml" != path.name:
        raise ValueError(f"{path.name}: file name must be '{compiled['id']}.yaml'")
    return compiled


def index_entry(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": profile["id"],
        "name": profile["name"],
        "status": profile["status"],
        "demo": profile.get("demo", False),
        "university": profile["university"],
        "faculty": profile.get("faculty"),
        "degree_level": profile["degree_level"],
    }


def compile_all(src: Path = PROFILES_DIR, out: Path = OUTPUT_DIR) -> list[dict[str, Any]]:
    profiles = [compile_profile_file(p) for p in sorted(src.glob("*.yaml"))]
    out.mkdir(parents=True, exist_ok=True)
    for profile in profiles:
        text = json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=False)
        (out / f"{profile['id']}.json").write_text(text + "\n", encoding="utf-8")
    # Real profiles first, the demo last; then alphabetical.
    index = sorted((index_entry(p) for p in profiles), key=lambda e: (e["demo"], e["id"]))
    (out / "index.json").write_text(
        json.dumps({"version": 1, "profiles": index}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", type=Path, default=PROFILES_DIR)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    profiles = compile_all(args.src, args.out)
    for p in profiles:
        print(f"compiled {p['id']} ({p['status']}, {len(p['rules'])} rules) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
