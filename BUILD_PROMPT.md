# BUILD PROMPT — "ThesisCheck" (working name): offline thesis format checker PWA

You are building this project in this repository. Work in the 8 stages in §17, in
order. At the end of each stage: run its test, show me the output, commit, and stop
for my OK before the next stage. I am a beginner: explain what you did in plain words
after each stage, and write code comments for a beginner.

Items marked **(assumed)** are defaults I may change. Ask me before changing anything
not marked (assumed). Items marked **TODO(source)** must not be invented: they wait
for the faculty formatting guideline.

**Sources received so far** (in `docs/sources/`): RTU FCSITE slides "AI generated
text, Academic integrity assessment" (EN) and "Academic integrity in theses" (2026),
both by G. Jēkabsons. They define referencing and AI-disclosure rules but contain NO
page-layout or typography rules. Every PAGE/TEXT/HEAD/PGNUM/FIG/TAB value in the RTU
profile stays `TODO(source)` until I add the faculty formatting guideline. Until then,
stage 1 uses a clearly labelled DEMO profile and lists each value I must confirm.

> **Decisions log** (changes agreed with the owner after this prompt was written):
> - 2026-11-10: `pydantic==2.14.3` cannot be installed together with
>   `typing-extensions==4.15.0` (2.14.x needs ≥ 4.16.0). Agreed: use
>   `pydantic==2.13.5` (dev/build only) so dev and Pyodide share typing-extensions 4.15.0.

---

## 1. Goal & scope
ThesisCheck is an installable web app (PWA) for phones and computers. A student
picks their university profile, opens their thesis (.docx), and gets: every
formatting and referencing violation grouped by category, a 0–100 readiness score,
a one-tap auto-fix that produces a NEW corrected .docx, an annotated .docx with a
Word comment on every problem not fixed, and a before/after score. Everything runs
in the browser on the user's device. The thesis is never uploaded. No logins. Works
offline after the first visit. Checking is free. Fixing and the annotated copy need
a licence key.

**Positioning** (README, landing screen, report footer): "ThesisCheck checks
formatting and referencing. It is not a plagiarism or AI-text detector and does not
judge academic integrity — at RTU, people make those decisions." Never output
wording that suggests a thesis is "plagiarism-free" or "AI-free".

**v1 must-haves:** one profile — RTU, Faculty of Computer Science, Information
Technology and Energy (FCSITE), programme TODO(source); checker; auto-fix; annotated
copy; score before/after; HTML report (printable to PDF); submission checklist;
works on a 360 px phone and a desktop; installable; fully offline after first load;
licence key unlock.

**Out of scope for v1:** AI assistant (phase 2), LaTeX, .doc/.odt input (show a
conversion hint), plagiarism or AI-text detection (ever), sync between devices,
accounts, .docx→PDF conversion, PDF guideline import, editing profiles in the app.

**Definition of done (v1):**
- All rules in §5 implemented, each with a passing pytest.
- Fix → re-check raises the score on every sample; the original file's SHA-256 is
  unchanged; the plain text of the fixed copy equals the original except for removed
  empty paragraphs.
- Playwright passes at 360×780 (phone) and 1440×900 (desktop), including with the
  network off after first load.
- axe-core: no serious or critical issues.
- §8 budgets met and measured in `docs/perf.md`.
- With DevTools open during check→fix→download, zero requests leave the app's origin.
- Deployed to the static host and installed on a real Android phone and iPhone.

## 2. Stack & libraries (pin EXACTLY these versions; no `^` or `~`)
Versions checked 2026-11-10.

Runtime (shipped to users):
| Name | Version | Licence | Role |
|---|---|---|---|
| pyodide | 314.0.7 | MPL-2.0 (do not modify its files) | Python 3.14 in a Web Worker |
| python-docx | 1.2.0 | MIT | Read/write .docx incl. native comments (`Document.add_comment`); wheel `python_docx-1.2.0-py3-none-any.whl` loaded via micropip from a LOCAL path |
| lxml | 6.1.3 | BSD-3 | Raw XML access; from Pyodide's package set |
| typing-extensions | 4.15.0 | PSF | python-docx dependency; from Pyodide's package set |
| svelte | 5.57.3 | MIT | UI |
| @lucide/svelte | 1.71.0 | ISC | Icons |
| dexie | 4.4.7 | Apache-2.0 | IndexedDB: history, settings, licence |
| zod | 4.6.7 | MIT | Validate worker messages + stored records |
| workbox-window | 7.4.1 | MIT | Peer dep of vite-plugin-pwa (update prompt) |
| @noble/ed25519 | 3.2.0 | MIT | Lazy-loaded ONLY if Web Crypto Ed25519 is unsupported |

Build/dev only: vite 8.3.7, @sveltejs/vite-plugin-svelte 7.3.1, vite-plugin-pwa
2.0.0, tailwindcss 4.3.5, @tailwindcss/vite 4.3.5, typescript 6.0.3 (NOT 7.x —
svelte-check 4.7.8 supports ≤6), svelte-check 4.7.8, vitest 5.1.0,
@playwright/test 1.65.0, @axe-core/playwright 4.14.0 (MPL-2.0, dev only), prettier
3.9.10, prettier-plugin-svelte 4.1.1, eslint 10.14.0, eslint-plugin-svelte 3.24.1.

Python dev (Python 3.14 to match Pyodide), in `engine/requirements-dev.txt`, venv:
python-docx==1.2.0, lxml==6.1.3, typing-extensions==4.15.0, pydantic==2.14.3
(→ 2.13.5, see decisions log), PyYAML==6.0.3, pytest==9.2.0, ruff==0.17.4.

Deliberately NOT used: Comlink (no release since 2024-11; typed postMessage + Zod
instead), pdf-lib (unmaintained), jsPDF (print stylesheet gives PDF for 0 KB),
citeproc-js (CPAL/AGPL — never), pyspellchecker (too big for phones, no Latvian;
curated UK↔US list instead), Pydantic/PyYAML at runtime (validated at build time).

Rules: NO CDN at runtime. `scripts/fetch-pyodide.mjs` copies the needed Pyodide
files (pyodide.mjs, pyodide.asm.mjs, pyodide.asm.wasm, python_stdlib.zip,
pyodide-lock.json, lxml + typing-extensions + micropip wheels and deps) into
`public/pyodide/`, and the python-docx wheel into `public/wheels/`, then verifies
each SHA-256 against `scripts/pyodide-files.lock.json`. Add no library not listed
here without asking me.

## 3. Project structure
```
engine/                       Plain Python rules engine — NO browser code, ever
  thesischeck/
    __init__.py               Public API: check(), fix(), annotate(), score()
    api.py                    Entry functions called by both pytest and the worker
    __main__.py               CLI: python -m thesischeck check|fix|annotate …
    docx_io.py                Safe open: zip limits, XXE-safe parser, reject macros
    model.py                  Dataclasses: Finding, Report, Location, Profile (stdlib only)
    profile_loader.py         Loads compiled profile JSON into dataclasses
    document_view.py          Read-only snapshot built once per check
    rules/
      registry.py             @rule decorator; maps rule ID → check fn and fix fn
      page_setup.py text.py headings.py page_numbers.py structure.py toc.py
      figures_tables.py citations.py consistency.py title_page.py ai_disclosure.py
    checker.py                Runs enabled rules on a DocumentView → findings (READ ONLY)
    fixer.py                  Copies bytes → applies fix fns → NEW bytes (ONLY writer)
    annotator.py              Copies bytes → one Word comment per unfixed finding
    scoring.py                Score formula (§4c)
    data/uk_us_pairs.tsv      ~1,800 UK↔US spelling pairs
    data/ai_tools.txt         Known AI developers/tools (editable, no code change)
  profiles/
    rtu-fcsite-<level>.yaml   One file per university/programme (source of truth)
    demo.yaml                 Clearly labelled DEMO profile used until sources arrive
  schema/profile_schema.py    Pydantic models — validate YAML at build/test time
  tools/compile_profiles.py   YAML → validated → public/profiles/*.json + index.json
  tools/make_samples.py       Generates tests/samples/*.docx, each breaking ONE rule
  tests/                      test_rules_*.py, test_fix_roundtrip.py, test_security.py,
                              test_profiles.py, test_no_browser_imports.py, samples/
  requirements-dev.txt  pyproject.toml
src/                          Svelte app
  main.ts  App.svelte  app.css
  lib/worker/engine.worker.ts client.ts messages.ts
  lib/db.ts licence.ts files.ts report-html.ts capabilities.ts
  components/                 ProfilePicker FileDrop EngineProgress ScoreDial FindingList
                              FindingItem FixPanel Checklist InstallPrompt OfflineBadge
                              LicenceDialog ErrorPanel
public/_headers  public/icons/   (pyodide/ wheels/ engine/ profiles/ generated, gitignored)
scripts/fetch-pyodide.mjs pack-engine.mjs perf-budget.mjs
tests-e2e/                    Playwright: phone, desktop, offline, a11y, no-external-requests
docs/                         sources/ perf.md how-to-add-a-university.md licence-keys.md privacy.md
.claude/skills/               Project skills (see Add-ons)
tools-private/                NOT in repo (gitignored): sign_key.py + private key
```

## 4. Core features (in the order the user meets them)
a. **Pick profile, then file.** Profile list from `profiles/index.json` (v1: one,
   preselected). Phones: `<input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document">`.
   Computers: the same plus drag-and-drop on the whole window. Check the size cap
   (§8) BEFORE reading the file into an ArrayBuffer.
b. **Report.** Findings grouped by category (Page setup, Text, Headings, Page
   numbers, Structure, Contents, Figures & tables, Citations & references, AI
   disclosure, Consistency, Title page), collapsible, with per-severity counts. Each
   item: rule name + ID, the university's rule in plain words with `guideline_ref`,
   what was found, where (page estimate, section, heading path, ~60-char snippet),
   severity (icon + word), "Auto-fixable" or "Fix by hand" + one-line how-to. Filter
   by severity; sort by document order or severity.
c. **Readiness score (0–100), fixed formula in `scoring.py`:**
   weights error 5, warning 2, info 0.5; penalty = Σ weight × min(count per rule, 5);
   score = round(100 × e^(−penalty/60)), clamped 0–100; if any `blocking` rule fails
   (missing title-page field, missing required section) the score is capped at 69.
   Bands: 90–100 "Ready", 70–89 "Nearly ready", 0–69 "Needs work". The UI shows the
   formula under "How is this calculated?".
d. **One-tap auto-fix (paid).** The worker gets a structured CLONE of the original
   bytes (never a transfer). The fixer works on a copy, applies every fix the profile
   allows, re-checks, returns `<name>_fixed.docx`. **Auto-fix is formatting-only: it
   never changes, adds or removes a word of the student's text** (only empty
   paragraphs may be removed). So the fixed copy needs no AI disclosure; say so in
   help. Save via `navigator.share({files})` when `canShare` allows, else download.
e. **Annotated copy (paid).** `<name>_annotated.docx` = fixed copy + one Word
   comment (author "ThesisCheck") per remaining finding: "[CITE-04] Quoted text has
   no reference. RTU rule: … How to fix: …". Findings with no text anchor go on the
   first paragraph of the affected section.
f. **Before/after + export.** Score dial before → after, list of fixes, "Export
   report" → standalone HTML (inline CSS, no scripts) with print stylesheet.
g. **Submission checklist** (from profile `manual_checklist`, ticks stored in Dexie):
   - If any AI tool generated text or images, each use is referenced (developer,
     tool, prompt, link to chat, access date).
   - AI tools used (also for grammar or translation) are named with their purpose in
     the Introduction ("Tools used in writing this thesis").
   - Directly copied or directly translated text is in quotation marks with a
     reference (maths excepted).
   - References are placed where the source is used, not only at paragraph end.
   - Reused parts of my own earlier work (e.g. bachelor thesis) are referenced.
   - Supervisor has signed; declaration of originality signed; upload to the RTU
     system done; Latvian and English abstracts say the same thing (assumed).
h. **Install + offline.** "Install app" via `beforeinstallprompt`; iOS Safari
   one-time sheet "Share → Add to Home Screen". Header badge: "Works offline ✓" when
   cached; "Offline — everything still works"; "Update ready — reload".

## 5. Checks (each rule = one function with an ID, check fn, optional fix fn)
Every expected value comes from the profile, never hard-coded. Work in twips/EMU
internally, show cm/pt. `guideline_ref` on every rule.

| ID | Check | Fix? |
|---|---|---|
| PAGE-01 | Margins per section within ±0.05 cm — TODO(source) | Yes |
| PAGE-02 | Paper size A4 (assumed) | Yes |
| PAGE-03 | Portrait, except sections allowed landscape (margins checked rotated) | No |
| PAGE-04 | Gutter/mirror margins off unless profile says so | Yes |
| TEXT-01 | Body font family (resolved run → para style → basedOn chain → docDefaults → theme) — TODO(source) | Yes |
| TEXT-02 | Body font size — TODO(source) | Yes |
| TEXT-03 | Line spacing — TODO(source) | Yes |
| TEXT-04 | Body alignment (justified, assumed) | Yes |
| TEXT-05 | Paragraph spacing before/after — TODO(source) | Yes |
| TEXT-06 | First-line indent — TODO(source) | Yes |
| TEXT-07 | Direct formatting overriding the body style on >X% of a paragraph | Yes |
| TEXT-08 | >1 consecutive empty paragraph used for spacing | Yes (remove) |
| HEAD-01 | Headings use Heading 1–3 styles, not bold body text | No |
| HEAD-02 | Heading font/size/bold/spacing per level — TODO(source) | Yes |
| HEAD-03 | No skipped levels | No |
| HEAD-04 | Numbering format per profile; unnumbered Introduction/Conclusions/References | Yes if Word list numbering; No if typed |
| HEAD-05 | Capitalisation per level — TODO(source) | Yes (style caps, never retyping) |
| HEAD-06 | Level-1 headings start on a new page | Yes |
| PGNUM-01 | Page number field present | Yes |
| PGNUM-02 | Position and format — TODO(source) | Yes |
| PGNUM-03 | Title page shows no number; counting start — TODO(source) | Yes |
| STRUCT-01 | Required sections present (from profile) | No |
| STRUCT-02 | Required sections in order | No |
| STRUCT-03 | Abstract word counts within limits (each language) — report only, never shortened | No |
| STRUCT-04 | Main-text word/page count within limits | No |
| STRUCT-05 | Introduction contains a "Tools used in writing this thesis" paragraph (phrases per language in profile). Info: required only if AI tools were used (AI slides p.5) | No |
| TOC-01 | TOC field exists | No |
| TOC-02 | TOC entries match real headings (text + level) | No ("Right-click → Update field") |
| TOC-03 | TOC looks out of date | Yes (`w:updateFields`, explained) |
| FIG-01..04 | Caption present with profile label; sequential per chapter; caption position; mentioned in text | No |
| TAB-01..04 | Same for tables | No |
| LIST-01 | List of figures/tables (if required) matches captions | No |
| CITE-01 | Every in-text citation has a reference entry | No |
| CITE-02 | Every reference entry is cited | No |
| CITE-03 | Citation format matches profile style (author–date `(Author, 2026)`, assumed) | No |
| CITE-04 | Quoted passage („…", "…", "…", ≥8 words) with no citation in the same or next sentence; equations excluded (Plagiarism slides p.6) | No |
| CITE-05 | Paragraph >120 words (assumed) with zero citations in chapters marked `literature_review: true`. Info (Plagiarism slides p.5) | No |
| REF-01 | Reference has author, year, title; online sources have URL + access date | No |
| REF-02 | Reference-list order (alphabetical for author–date, assumed) | No |
| REF-03 | Reference-list formatting (hanging indent, spacing) | Yes |
| REF-04 | Wikipedia / encyclopedia / lecture slides → info "secondary source — also cite a primary source" (Plagiarism slides p.5) | No |
| REF-AI-01 | AI-tool reference matches `Developer. Tool [version]. Prompt: <prompt>. <URL>. [accessed DD.MM.YYYY.].` (all parts present) and has an in-text citation `(Developer, YYYY)`. Detected via `data/ai_tools.txt` (AI slides p.4) | No |
| CONS-01 | Mixed UK/US spelling in English text (flag the minority) | No |
| CONS-02 | Abbreviation used before being defined or listed | No |
| CONS-03 | Same term written different ways (e-mail/email, dataset/data set) | No |
| TITLE-01 | Title page fields present — list TODO(source) | No |
| TITLE-02 | Title-page year = current year (warning) | No |

Language per paragraph: `w:lang`, else heuristic (āčēģīķļņšūž → lv). CONS-01 only on
English text.

## 6. Data model / contracts (every object has `version`)
a. **Rule profile (YAML → compiled JSON):**
```yaml
version: 1
id: rtu-fcsite-bachelor
status: draft            # draft | verified — UI shows "Draft profile" banner if draft
university: Riga Technical University
faculty: Faculty of Computer Science, Information Technology and Energy
degree_level: bachelor   # bachelor | master (assumed both, one file each)
languages: [lv, en]      # (assumed)
citation_style: author-date   # (assumed; evidence: "(OpenAI, 2026)" in AI slides p.4)
date_format: "DD.MM.YYYY."
sources:
  - {id: ai-slides, title: "AI generated text, Academic integrity assessment", file: docs/sources/rtu-fcsite-ai-generated-text-academic-integrity-EN.pdf}
  - {id: plag-slides, title: "Academic integrity in theses (2026)", file: docs/sources/rtu-fcsite-academic-integrity-in-theses-2026.pdf}
rules:
  PAGE-01: {expected: TODO, severity: error, autofix: true, rule_text: "...", guideline_ref: TODO}
  REF-AI-01: {severity: error, autofix: false, rule_text: "If content was generated by an AI tool, give a reference: Developer. Tool and version. Prompt: … Web address. [accessed date].", guideline_ref: "ai-slides p.4"}
  # … one entry per rule ID; omitted = disabled; TODO values = rule disabled + listed in the UI as "not yet checked"
structure: {required_sections: [...], word_limits: {...}, literature_review_headings: [...]}
captions: {figure: {...}, table: {...}}
ai_disclosure: {heading_phrases: {en: ["Tools used in writing this"], lv: [TODO]}}
manual_checklist: [...]
```
Pydantic validates in pytest and `compile_profiles.py` (a `TODO` value is allowed
only with `status: draft`). The browser reads compiled JSON with stdlib only.

b. **Finding:** `{version, id, rule_id, category, severity, message, rule_text,
guideline_ref, location:{part, paragraph_index, section_index, page_estimate,
heading_path, snippet}, expected, found, fixable, fixed, how_to_fix}`

c. **Report:** `{version, engine_version, document_sha256, file_name,
profile:{id, version, status}, created_at, stats:{paragraphs, pages_estimate, words},
findings, score:{value, band, penalty, capped}, skipped_rules:[{rule_id, reason}]}`

d. **Worker messages** (Zod; all have `{version:1, id, type}`):
UI → worker: `init`, `check {profileId, fileName, bytes}`, `fix {profileId, bytes}`,
`annotate {profileId, bytes}`, `cancel {targetId}`.
Worker → UI: `progress {stage, pct, detail}`, `ready {engineVersion, pyodideVersion}`,
`result {report}`, `fileResult {kind, bytes, report}`, `error {code, message, detail}`.
Codes: ENGINE_LOAD_FAILED, FILE_TOO_LARGE, NOT_DOCX, LEGACY_DOC, ODT, ENCRYPTED,
MACRO_DOCM, CORRUPT, ZIP_BOMB, OUT_OF_MEMORY, TIMEOUT, INTERNAL.

## 7. Separation rules
- `engine/thesischeck` never imports `js`/`pyodide` (a test enforces it).
- Check fns get a read-only `DocumentView`; only `fixer.py`/`annotator.py` write,
  always on a copy.
- Checker, fixer, annotator, scoring, UI and (phase 2) `src/lib/ai/` are separate
  modules; UI → engine only via `worker/client.ts`.
- New university = one YAML file + `compile_profiles`; a test proves a dummy second
  profile works with no code change.
- Everything builds and passes with `src/lib/ai/` deleted.

## 8. Performance on phones
- Shell renders first; worker starts after first paint; progress shows MB + stage;
  the user can pick profile and file while the engine loads.
- **Budgets** (enforced by `scripts/perf-budget.mjs`, measured in `docs/perf.md`):
  shell ≤ 250 KB compressed, first paint ≤ 2 s on Fast 4G; engine total ≤ 9 MB
  compressed (Pyodide wasm alone ≈ 3.6 MB gzipped); engine ready ≤ 8 s first visit /
  ≤ 3 s cached on a mid-range phone (Pixel 6a / Galaxy A54 class); 100-page check
  ≤ 10 s, fix + re-check ≤ 20 s. Build `DocumentView` once per run.
- Service worker precaches shell and `/pyodide/ /wheels/ /engine/ /profiles/`
  (CacheFirst, versioned). `navigator.storage.persist()` after first check.
- Input cap 50 MB (assumed), uncompressed cap 200 MB; warn above 20 MB on iOS or
  `deviceMemory ≤ 2`. Progress every 50 paragraphs; `cancel` terminates the worker.

## 9. Errors & edge cases (friendly messages)
| Case | Message |
|---|---|
| Password-protected | "This file is password-protected. Remove the password in Word (File → Info → Protect Document), save, and try again." |
| Corrupt | "This file looks damaged. Open it in Word, use File → Save As .docx, and try again." |
| .doc | "This is an old .doc file. Open it in Word or LibreOffice and save as .docx." |
| .odt | "This is an OpenDocument file. In LibreOffice choose File → Save As → Word (.docx)." |
| .docm / macros | "Files with macros aren't accepted, for your safety. Save as a normal .docx." |
| Tracked changes | Checked as if accepted; banner says so; fixed copy keeps them. |
| Direct formatting | Explained in TEXT-07; fixer removes only conflicting properties. |
| Different margins per section | Findings name the section. |
| Landscape pages | Allowed if profile allows; never auto-rotated. |
| Footnotes | Excluded from body font rules; scanned by CITE rules. |
| Text boxes | Read for citations/captions; not auto-fixed; info finding. |
| Equations | Skipped by text rules and CITE-04; never modified. |
| RTL / non-Latin | Complex-script fonts via `w:cs`; consistency rules skip; info. |
| 300+ pages | "Big thesis — this can take a minute on a phone." + cancel. |
| Pyodide fails | "The checking engine couldn't start. Check your connection for the first visit, then reload. After that it works offline." + Retry |
| Old browser | "Your browser is too old for ThesisCheck. Please update Chrome, Safari, Edge or Firefox." |
| Storage full | "Your device is out of storage space, so the app can't save offline files. Free some space; checking still works while online." |
| iPhone cleared data | "The offline files were cleared by your iPhone. Reloading them now…" + advise home-screen install; ask to paste licence key again. |
| First visit offline | "You need a connection the first time to download the app (~9 MB). After that it works offline." |
| Out of memory | "Your phone ran out of memory for this file. Try closing other apps, or use a computer." |
| No headings / TOC / references | `skipped_rules` with a reason, not false errors. |
| Draft profile | Banner: "This profile is a draft — some rules are not checked yet." |

## 10. Safety and privacy
- `docx_io.py` before python-docx: ≤50 MB compressed, ≤200 MB uncompressed, ≤2,000
  entries, ratio ≤100:1 per entry, no `..`/absolute entry names.
- Own XML parsing: `etree.XMLParser(resolve_entities=False, no_network=True,
  load_dtd=False, huge_tree=False)`; reject any part with `<!DOCTYPE`. XXE and
  billion-laughs tests.
- Never execute anything; reject `.docm` / `vbaProject.bin`. External links / remote
  templates: report (info), don't alter.
- CSP via `_headers` + `<meta>` fallback: `default-src 'self'; script-src 'self'
  'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self'; img-src 'self'
  data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self'; object-src 'none';
  base-uri 'none'; form-action 'none'; frame-ancestors 'none'` (verify Pyodide needs
  nothing more; document any addition).
- No analytics, third-party scripts, remote fonts or error reporting.
  `docs/privacy.md` explains how to verify in DevTools → Network.
- Dexie stores report JSON + file name + hash, NEVER thesis bytes. "Delete all
  history" in settings.

## 11. UI/UX
Single column 360–767 px, two columns ≥1024 px. Touch targets ≥44 px, base text
16 px, no horizontal scroll at 360 px. Light/dark via `prefers-color-scheme` + toggle.
State machine: empty → engine-loading → checking → results → fixing → fixed → error.
Save via share sheet or `<a download>` (Blob URL revoked after). Persists: profile,
theme, licence key, last 20 checks (date, name, profile, scores), checklist ticks.
Never file contents. UI language English with Latvian strings planned (assumed: EN
first, i18n-ready string table).

## 12. Accessibility
Keyboard-complete (logical Tab order, Enter/Space, Esc closes dialogs, focus trap +
return), visible 2 px focus ring, ARIA labels on icon buttons, `aria-live` for
progress/results, WCAG AA contrast both themes, severity = icon + word, reduced
motion respected, `lang` set; axe run on every state.

## 13. Paid fix (licence keys)
- Free: full report, score, checklist, HTML export. Paid: auto-fix + annotated copy.
- Price €9 one-time, key valid 90 days (assumed). Payment: Lemon Squeezy as merchant
  of record (EU VAT handled) (assumed). v1: I sign and email keys manually.
- Key: `TC1.<base64url(payload)>.<base64url(sig)>`, payload
  `{"v":1,"kid":"k1","sku":"fix","iat":"YYYY-MM-DD","exp":"YYYY-MM-DD","oid":"…"}`,
  Ed25519. Public keys by `kid` in `licence.ts`.
- Verify with `crypto.subtle` Ed25519; on failure to import, lazy-load
  @noble/ed25519. Re-verify on launch. Expiry uses device clock (accepted weakness).
- `tools-private/sign_key.py` + private key are gitignored; a pre-commit check
  rejects files containing "PRIVATE KEY". `docs/licence-keys.md` documents it.
- Honesty note in docs: anyone can bypass a browser-only check with DevTools. At €9
  for students this is acceptable; no obfuscation or DRM.

## 14. Hosting
Cloudflare Pages (assumed): free, unlimited bandwidth, `_headers`, 25 MB/file
(Pyodide's largest ≈9.2 MB). README compares Netlify and GitHub Pages (no custom
headers). `_headers`: CSP; `*.wasm` → `application/wasm`; `/sw.js`, `/index.html` →
`no-cache`; hashed assets and `/pyodide/*` → `max-age=31536000, immutable`;
`nosniff`; `Referrer-Policy: no-referrer`; restrictive `Permissions-Policy`.
Updates: vite-plugin-pwa `registerType: 'prompt'`, versioned cache names, old caches
deleted on activate. Publish = push to `main` (host builds) or upload `dist/`.

## 15. Testing
- `make_samples.py` generates `clean.docx` + one sample per rule ID; commit them.
- One pytest per rule: clean → no finding; bad sample → exactly that finding; if
  fixable, fix → re-check → none.
- Roundtrip: score_after ≥ score_before; input SHA-256 unchanged; output opens;
  comments part valid; plain text unchanged except removed empty paragraphs.
- Security: zip bomb, entry count, path traversal, XXE, billion laughs, .docm,
  encrypted OLE, random bytes.
- `tests/private/` (gitignored) for my real thesis: full run + timing if present.
- Vitest: licence (valid, tampered, expired, unknown kid, noble fallback), Zod
  schemas, score display.
- Playwright on `vite preview`: phone (Pixel 7, iPhone 15) and desktop 1440×900;
  pick → results → test key → fix → download; drag-drop; axe per state; offline
  (load, `setOffline(true)`, reload, full check + fix); fail on any cross-origin
  request.

## 16. README & code style
README: what it is, positioning statement, privacy promise + how to verify, dev,
build, deploy, library table, budgets. `docs/how-to-add-a-university.md`. Ruff,
Prettier, ESLint, type hints, short functions, beginner comments explaining WHY.

## 17. Build stages (test → show output → commit → wait for my OK)
1. **Engine core.** `docx_io`, `DocumentView`, schema + compiler, `demo.yaml` and a
   draft `rtu-fcsite-bachelor.yaml` (filled where the sources say; everything else
   TODO with a list for me), sample generator, rules PAGE-01, PAGE-02, TEXT-01,
   TEXT-02, HEAD-03; CLI. Test: pytest green; CLI on `clean.docx` → 0 findings.
2. **All rules + score + security.** Test: one test per rule green; CLI on my real
   thesis gives a sensible report (I review).
3. **Fixer + annotator.** Test: roundtrip green; annotated file opens in Word/
   LibreOffice with comments (I check one manually).
4. **Engine in the browser.** Worker, fetch-pyodide, Zod messages, bare page. Test:
   Playwright check + fix in Chromium equals pytest report JSON for the same sample;
   sizes and load time → `docs/perf.md`.
5. **Responsive UI.** All components/states, report export, checklist, a11y. Test:
   Playwright phone + desktop + axe green; screenshots at 360 and 1440 px.
6. **Offline, install, licence.** Test: offline + no-external-requests + Vitest
   licence tests green.
7. **Hosting + release.** Test: `curl -I` headers on live URL; install on real
   Android + iPhone; full check in airplane mode; phone timing in `docs/perf.md`.
   Tag `v1.0.0`.
7b. **Launch assets with Higgsfield MCP** (see "Higgsfield MCP" section). Optional;
   app works and ships without it.
8. **AI assistant (phase 2)** — only after I approve v1.

## 18. Deliverables
- Run locally: `npm ci && npm run setup` once, then `npm run dev`.
- Build for publishing: `npm run build` → `dist/`.
- All tests: `npm test` (pytest + vitest + playwright).

## Phase 2: AI assistant (optional module `src/lib/ai/`)
- WebLLM (@mlc-ai/web-llm 0.2.87, Apache-2.0) over a local Ollama server (Ollama
  needs an install, a running server, CORS and a localhost CSP hole). Computer-only
  (assumed): shown only with WebGPU on a non-phone device.
- Model: ~1–2 B instruct, q4f16, ~1 GB, permissive licence verified (reject
  non-commercial). Weights hosted on our own origin (re-shard ≤25 MB) so CSP stays
  `connect-src 'self'`; only if impossible, one extra host after explicit opt-in,
  documented in privacy.md.
- Download UX: size warning + progress + cancel; "Remove AI model" in settings.
- **Allowed jobs only:** (1) explain a finding, quoting `rule_text` +
  `guideline_ref`; (2) answer formatting/referencing questions from the profile;
  (3) draft a rule profile from a guideline PDF (pdfjs-dist 6.5.438) — developer tool,
  not shipped to students.
- **Removed:** abstract shortening (RTU slides: rewriting is text generation and must
  be referenced). Reference repair is deterministic code (form fields → formatted
  string in profile style), no LLM.
- The AI never receives or returns thesis prose; system prompt and UI offer no
  write/rewrite action. Every answer is a preview the user dismisses or copies;
  nothing is applied to the document.
- Prompts in `src/lib/ai/prompts/*.md`, temperature 0.2, ≤400 tokens, 30 s timeout,
  streaming. Output must cite a rule ID that exists in the profile, else "The
  assistant couldn't produce a reliable answer."

## Add-ons (ask me before installing anything)
Agent skills — read each SKILL.md and script first, show this table, install into
`./.claude/skills/` only after I approve:
| Name | Repo | Purpose | Scripts | Risks |
|---|---|---|---|---|
| docx | github.com/anthropics/skills | OOXML comments, tracked changes, validation | Python unpack/pack/validate; may call LibreOffice | Runs local scripts |
| skill-creator | github.com/anthropics/skills | Writing project skills | Python evals | Low |
| webapp-testing | github.com/anthropics/skills | Playwright helpers | Starts servers, Playwright | Starts processes |
| pdf | github.com/anthropics/skills | Read guideline PDFs to draft profiles | pypdf/pdfplumber | Untrusted PDF parsing, local only |
| frontend-design | github.com/anthropics/skills | Non-generic UI direction | None | Low |

Custom project skills (show each SKILL.md before saving; keep updated):
1. `thesischeck-new-rule` — ID naming, read-only check fn, optional fix fn, profile
   entry with guideline_ref, sample, test, docs line.
2. `thesischeck-contracts` — profile/finding/report/message formats, versioning,
   the messages-only boundary.
3. `thesischeck-testing` — ruff → pytest → compile profiles → vitest → playwright
   phone/desktop/offline → perf budget.

## Higgsfield MCP (marketing assets — developer-side only)
Higgsfield is a cloud image/video/audio generation service with an MCP connector.
It is used ONLY by me and Claude Code to make launch and marketing material. It is
NEVER part of the app.

**Setup (verify before use):** official connector, URL as shown on Higgsfield's
"What is Higgsfield MCP" help page (currently `https://mcp.higgsfield.ai/mcp`;
some guides show `https://mcp.higgsfield.ai`). Sign-in is OAuth with my Higgsfield
account; no API key. Add it with
`claude mcp add --transport http higgsfield <URL>` at **user scope**, never in the
repo's `.mcp.json`. Do NOT use the unofficial community servers (geopopos,
jfikrat): they need an API key + secret in env vars and are unvalidated.

**Hard rules:**
- Runtime separation: the app never calls Higgsfield. No Higgsfield URL may appear
  in `src/`, `public/`, `engine/` or the CSP. The no-external-requests Playwright
  test and a grep test (`higgsfield` must not occur outside `marketing/` and this
  file) enforce it.
- No thesis content: prompts and reference images use only the synthetic demo
  thesis from `tools/make_samples.py` and app screenshots of it. Never a real
  student's document, name or text.
- No RTU branding: no RTU logo, crest, name in logo form or campus imagery in
  generated assets (trademark + would imply endorsement). Say "for RTU students"
  in text only.
- Credits cost money: MCP generations deduct my credits at standard rates (no
  unlimited plan perks). Before EVERY generation, show me the model, prompt,
  count and estimated credits and wait for my OK. Default to 1 take, not 4.
- Honest product shots: videos and images show the real app UI (Playwright
  screenshots/recordings as reference). Never show features the app doesn't have,
  "AI detector" or "plagiarism check" claims, or fake scores.
- Disclose: marketing pages that use generated imagery/video carry "Includes
  AI-generated visuals".
- Check the Higgsfield terms for commercial use of outputs on my plan before
  publishing anything; record the plan + date in `marketing/LICENSES.md`.

**What to make with it (stage 7b):**
| Asset | Use | Notes |
|---|---|---|
| 15–30 s promo video (9:16 and 16:9) | Social, landing page | Built from real Playwright screen recordings; generated b-roll only for intro/outro |
| Hero image + 3 feature illustrations | Landing page | Exported to WebP ≤150 KB each, committed to `public/landing/` (self-hosted, no remote URLs) |
| App icon concepts | Exploration only | Final icon redrawn as clean SVG by hand/code; PWA icons generated from that SVG |
| Social post images (1:1, 4:5) | Launch posts | Text overlaid by me, not by the model (models garble text) |
| Short voice-over (EN, optional LV) | Promo video | Script written by me; model only reads it |

**Files:** `marketing/` (gitignored large originals in `marketing/raw/`, committed
finals in `marketing/final/`), `marketing/PROMPTS.md` (every prompt, model, date,
credits used), `marketing/LICENSES.md`.

**Stage 7b test:** grep test passes; no-external-requests test passes; landing
assets total ≤ 600 KB; Lighthouse performance on the landing page ≥ 90; I approve
each asset before commit.

## Open questions for me (do not block stage 1 on them)
1. Faculty formatting guideline (margins, fonts, headings, captions, page numbers,
   title page, required sections, word limits) — blocks the real RTU profile.
2. Bachelor, master or both? Latvian and English abstracts both required?
3. Citation style: author–date `(Author, 2026)` (assumed) or numeric `[1]`?
4. Price / payment provider / host — confirm €9, Lemon Squeezy, Cloudflare Pages.
5. Higgsfield plan: does it allow commercial use of outputs, and what credit
   budget per month for marketing?
