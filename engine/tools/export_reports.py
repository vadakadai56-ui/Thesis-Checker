"""Write the reports plain Python produces for some samples, as JSON files.

    python tools/export_reports.py --out DIR --now 2026-11-10T12:00:00+00:00

The browser tests (tests-e2e/) run the SAME samples through the engine inside
Chromium and require identical results — proving the browser build behaves
exactly like the engine tested by pytest.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR))

from thesischeck import annotate, check, fix  # noqa: E402
from tools.compile_profiles import PROFILES_DIR, compile_profile_file  # noqa: E402

SAMPLES_DIR = ENGINE_DIR / "tests" / "samples"


def _file_result(result: dict) -> dict:
    """The same shape the worker posts for fix/annotate (without the bytes)."""
    out = {
        "kind": result["kind"],
        "fileName": result["file_name"],
        "report": result["report"],
        "before": result["before"],
        "fixedFindings": result["fixed_findings"],
        "fixes": result["fixes"],
    }
    if "comments" in result:
        out["comments"] = result["comments"]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--profile", default="demo")
    parser.add_argument("--check", nargs="*", default=[])
    parser.add_argument("--fix", nargs="*", default=[])
    parser.add_argument("--annotate", nargs="*", default=[])
    parser.add_argument("--big", action="store_true", help="also write big.docx (100+ pages)")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now)
    profile = compile_profile_file(PROFILES_DIR / f"{args.profile}.yaml")
    args.out.mkdir(parents=True, exist_ok=True)

    def save(name: str, data: dict) -> None:
        (args.out / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    for sample in args.check:
        data = (SAMPLES_DIR / f"{sample}.docx").read_bytes()
        save(f"check-{sample}.json", check(data, profile, file_name=f"{sample}.docx", now=now))
    for kind, fn, samples in (("fix", fix, args.fix), ("annotate", annotate, args.annotate)):
        for sample in samples:
            data = (SAMPLES_DIR / f"{sample}.docx").read_bytes()
            result = fn(data, profile, file_name=f"{sample}.docx", now=now)
            save(f"{kind}-{sample}.json", _file_result(result))
    if args.big:
        (args.out / "big.docx").write_bytes(big_thesis())
    return 0


def big_thesis() -> bytes:
    """A synthetic thesis of 100+ pages with a formatting problem in every long
    paragraph (wrong font and line spacing) — for timing check and fix."""
    from tools.make_samples import LONG_SENTENCE, build_document, clean_blocks, to_bytes

    blocks = clean_blocks()
    at = blocks.index(("h1", "Conclusions"))
    extra: list[tuple] = []
    for chapter in range(3, 12):
        extra.append(("h1", f"{chapter}. Chapter {chapter}"))
        for section in range(1, 4):
            extra.append(("h2", f"{chapter}.{section}. Section {section}"))
            extra += [("p", LONG_SENTENCE * 14 + "(Example, 2024).")] * 9
    document = build_document(blocks[:at] + extra + blocks[at:])
    for paragraph in document.paragraphs:
        if paragraph.text.startswith("The invented teams"):
            paragraph.paragraph_format.line_spacing = 1.0
            paragraph.runs[0].font.name = "Arial"
    return to_bytes(document)


if __name__ == "__main__":
    sys.exit(main())
