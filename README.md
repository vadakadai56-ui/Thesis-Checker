# ThesisCheck (working name)

An offline thesis **format and referencing** checker for .docx files. It will become
an installable web app (PWA) that runs entirely on your device: your thesis is
never uploaded.

> ThesisCheck checks formatting and referencing. It is not a plagiarism or AI-text
> detector and does not judge academic integrity — at RTU, people make those
> decisions.

The full plan is in [BUILD_PROMPT.md](BUILD_PROMPT.md).

**Status: stage 2 of 8: all rules, readiness score, security.** For now there is
a Python rules engine with a command line. The web app arrives in stages 4–6.

## What works now

- Safe opening of .docx files. It rejects .doc, .odt, password-protected files,
  macros, damaged files, zip bombs and XML tricks (XXE, billion laughs).
- A read-only `DocumentView` that resolves Word's formatting layers (run →
  character style → paragraph style → basedOn chain → list level → document
  defaults → theme). It also reads fields (table of contents, page numbers),
  headers and footers per section, list numbering, tables, images, footnotes,
  text boxes and language.
- **All 53 rules of BUILD_PROMPT §5**, each tested with a synthetic sample that
  breaks exactly that rule.
- The **readiness score** (0–100, fixed formula in `engine/thesischeck/scoring.py`).
- Profiles: `demo` (made-up values, clearly labelled) and a draft
  `rtu-fcsite-bachelor`. The RTU layout values come from the official RTU thesis
  template (2024). Open items are in
  [docs/rtu-profile-open-items.md](docs/rtu-profile-open-items.md).

## Developer setup (engine)

Needs Python 3.14, the same version Pyodide uses in the browser.

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r engine/requirements-dev.txt
cd engine
../.venv/bin/python tools/compile_profiles.py   # YAML -> public/profiles/*.json
../.venv/bin/python tools/make_samples.py       # regenerate tests/samples/*.docx
../.venv/bin/pytest                             # run all tests
../.venv/bin/ruff check . && ../.venv/bin/ruff format --check .
```

Check a document:

```bash
cd engine
../.venv/bin/python -m thesischeck check tests/samples/clean.docx --profile demo
../.venv/bin/python -m thesischeck check my-thesis.docx --profile rtu-fcsite-bachelor --json
../.venv/bin/python tools/make_spelling_pairs.py  # regenerate the UK/US spelling list
```

Exit codes: `0` no findings, `1` findings, `2` usage problem, `3` file refused.

## Layout

```
engine/thesischeck/   the engine (plain Python, no browser code)
engine/profiles/      one YAML file per university/programme (source of truth)
engine/schema/        Pydantic validation of profiles (build/test time only)
engine/tools/         profile compiler, sample generator
engine/tests/         pytest suite + generated sample documents
docs/                 sources, open items for the RTU profile
```
