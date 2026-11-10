"""Command line:  python -m thesischeck check FILE.docx [--profile demo] [--json]

Run it from the `engine/` folder. Profiles are the COMPILED JSON files made by
`python tools/compile_profiles.py` (written to ../public/profiles/).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .api import check
from .model import EngineError
from .profile_loader import load_profile_file
from .rule_ids import CATEGORIES

# engine/thesischeck/__main__.py -> repo root is two folders up from this package.
DEFAULT_PROFILES_DIR = Path(__file__).resolve().parents[2] / "public" / "profiles"
SEVERITY_ICON = {"error": "✖ error", "warning": "▲ warning", "info": "ℹ info"}


def _resolve_profile_path(value: str, profiles_dir: Path) -> Path:
    """Accept either a profile ID ('demo') or a path to a compiled .json file."""
    as_path = Path(value)
    if as_path.suffix == ".json":
        return as_path
    return profiles_dir / f"{value}.json"


def _print_human(report: dict) -> None:
    prof = report["profile"]
    print(f"ThesisCheck {report['engine_version']} — {report['file_name']}")
    print(f"Profile: {prof['id']} (v{prof['version']}, {prof['status']})")
    stats = report["stats"]
    print(
        f"Document: {stats['paragraphs']} paragraphs, {stats['words']} words, "
        f"~{stats['pages_estimate']} pages"
    )
    findings = report["findings"]
    print(f"\n{len(findings)} finding(s)")
    for category, label in CATEGORIES.items():
        items = [f for f in findings if f["category"] == category]
        if not items:
            continue
        print(f"\n== {label} ==")
        for f in items:
            loc = f["location"]
            where = f"p.~{loc['page_estimate']}" if loc["page_estimate"] else ""
            print(f"  [{f['rule_id']}] {SEVERITY_ICON[f['severity']]}: {f['message']} {where}")
            print(f"      expected: {f['expected']} | found: {f['found']}")
            if loc["snippet"]:
                print(f"      at: “{loc['snippet']}”")
    if report["skipped_rules"]:
        print(f"\nNot checked ({len(report['skipped_rules'])}):")
        for s in report["skipped_rules"]:
            print(f"  [{s['rule_id']}] {s['reason']}")
    print(
        "\nThesisCheck checks formatting and referencing. It is not a plagiarism or "
        "AI-text detector and does not judge academic integrity."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="thesischeck")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "fix", "annotate"):
        p = sub.add_parser(name)
        p.add_argument("file", type=Path)
        p.add_argument("--profile", default="demo", help="profile ID or compiled .json path")
        p.add_argument("--profiles-dir", type=Path, default=DEFAULT_PROFILES_DIR)
        p.add_argument("--json", action="store_true", help="print the raw report JSON")
    args = parser.parse_args(argv)

    if args.command in ("fix", "annotate"):
        print(f"'{args.command}' arrives in stage 3.", file=sys.stderr)
        return 2

    profile_path = _resolve_profile_path(args.profile, args.profiles_dir)
    if not profile_path.exists():
        print(
            f"Profile not found: {profile_path}\nRun `python tools/compile_profiles.py` first.",
            file=sys.stderr,
        )
        return 2

    try:
        report = check(
            args.file.read_bytes(), load_profile_file(profile_path), file_name=args.file.name
        )
    except EngineError as err:
        print(f"{err.code}: {err.message}", file=sys.stderr)
        return 3

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    # Exit code 1 if anything was found, so scripts can use it.
    return 1 if report["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
