# ThesisCheck (working name)

An offline thesis **format and referencing** checker for .docx files. It will become
an installable web app (PWA) that runs entirely on your device: your thesis is
never uploaded.

> ThesisCheck checks formatting and referencing. It is not a plagiarism or AI-text
> detector and does not judge academic integrity — at RTU, people make those
> decisions.

The full plan is in [BUILD_PROMPT.md](BUILD_PROMPT.md).

**Status: stage 4 of 8: the engine runs in the browser.** There is a Python rules
engine with a command line, and a bare test page that runs the same engine inside
the browser (Pyodide in a Web Worker). The real interface arrives in stage 5.

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
- **Auto-fix** (`fixer.py`) writes a NEW `<name>_fixed.docx`. It changes
  formatting only (styles, paragraph settings, page setup, page numbers) and
  never a word: if the words of the fixed copy differ from the original's, it
  refuses. 20 rules can be fixed automatically.
- **Annotated copy** (`annotator.py`) is the fixed copy plus one Word comment
  (author "ThesisCheck") on every problem that is left.
- Profiles: `demo` (made-up values, clearly labelled) and a draft
  `rtu-fcsite-bachelor`. The RTU layout values come from the official RTU thesis
  template (2024). Open items are in
  [docs/rtu-profile-open-items.md](docs/rtu-profile-open-items.md).

## Run the app locally

Needs Node.js 22+ and the Python venv described below (profiles are compiled with it).

```bash
npm ci            # install the exact pinned packages
npm run setup     # once: download Pyodide + packages (SHA-256 checked), pack the engine, compile profiles
npm run dev       # start the test page at http://localhost:5173
```

`npm run build` writes the publishable site to `dist/`. `npm test` runs everything:
pytest, the message-schema tests (Vitest) and the browser tests (Playwright).
`npm run perf` measures sizes and writes [docs/perf.md](docs/perf.md).

Nothing is downloaded from other sites while the app runs: Pyodide and the Python
packages are copied into `public/` at setup time and served from the app's own
address. The browser tests fail if any request leaves the app's origin.

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
../.venv/bin/python -m thesischeck fix my-thesis.docx --profile rtu-fcsite-bachelor       # -> my-thesis_fixed.docx
../.venv/bin/python -m thesischeck annotate my-thesis.docx --profile rtu-fcsite-bachelor  # -> my-thesis_annotated.docx
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
src/                  the web app (Svelte); src/lib/worker/ is the only door to the engine
scripts/              setup/build scripts (fetch Pyodide, pack the engine, perf budget)
tests-e2e/            browser tests (Playwright)
docs/                 sources, open items for the RTU profile, perf.md
```
