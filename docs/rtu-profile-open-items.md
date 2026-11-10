# RTU profile — values waiting for you

File: `engine/profiles/rtu-fcsite-bachelor.yaml` (status: **draft**).

Rules whose value is `TODO` are **not checked**. The app lists them as "not yet
checked", so nothing is guessed. Please send the **FCSITE thesis formatting
guideline** (and tell me which programme). I'll fill these in from it, with a page
reference for each.

## A. Needs the faculty formatting guideline (TODO(source))

| Rule | What I need from the guideline |
|---|---|
| (profile) `programme` | Programme name(s) the profile covers |
| PAGE-01 | Margins: top / bottom / left / right in cm |
| PAGE-03 | Are landscape pages allowed, and where (appendices only?) |
| PAGE-04 | Gutter / mirror margins: allowed or not |
| TEXT-01 | Body font family |
| TEXT-02 | Body font size (pt) |
| TEXT-03 | Line spacing (e.g. 1.0 / 1.5 / exactly 18 pt) |
| TEXT-05 | Space before / after paragraphs (pt) |
| TEXT-06 | First-line indent (cm), or none |
| TEXT-07 | Is direct formatting checked at all, and from what % of a paragraph |
| TEXT-08 | Confirm: empty paragraphs used for spacing should be flagged |
| HEAD-01 | Confirm: headings must use Word heading styles |
| HEAD-02 | Per heading level: font, size, bold, spacing before/after |
| HEAD-04 | Heading numbering format ("1.", "1.1." …); which sections are unnumbered |
| HEAD-05 | Capitalisation per level (e.g. level 1 ALL CAPS?) |
| HEAD-06 | Must level-1 headings start on a new page? |
| PGNUM-01..03 | Page-number position, format, whether the title page is counted/shown, where counting starts |
| STRUCT-01/02 | Required sections and their order (title page, abstracts, contents, introduction, …) |
| STRUCT-03 | Abstract word limits (Latvian and English) |
| STRUCT-04 | Main text length limits (words or pages) |
| TOC-01..03 | Confirm a Word-generated table of contents is required |
| FIG-01..04, TAB-01..04 | Caption label ("Fig." / "att."), numbering (per chapter?), caption position (above/below) |
| LIST-01 | Are lists of figures / tables required? |
| CITE-01, CITE-02, REF-01, REF-03 | Reference-list format (hanging indent, spacing, required fields) |
| CONS-01..03 | Confirm you want these consistency checks for RTU |
| TITLE-01/02 | Title-page fields (author, supervisor, title, programme, city, year, …) |
| `structure`, `captions` | Same information as above, in structured form |
| `ai_disclosure.heading_phrases.lv` | Latvian wording of "Tools used in writing this thesis" |

## B. Assumed defaults — confirm or change

| Item | Current value | Where it comes from |
|---|---|---|
| PAGE-02 paper size | A4, **checked now** | BUILD_PROMPT (assumed) |
| TEXT-04 alignment | justified | BUILD_PROMPT (assumed) |
| HEAD-03 no skipped heading levels | **checked now**, warning | General practice. No RTU source yet; I marked it (assumed) |
| CITE-03 citation style | author–date `(Author, 2026)` | (assumed); evidence: example in ai-slides p.4 |
| CITE-05 threshold | 120 words | BUILD_PROMPT (assumed) |
| REF-02 reference order | alphabetical | BUILD_PROMPT (assumed) |
| degree level | bachelor (master gets its own file) | (assumed) |
| languages | lv, en | (assumed) |
| severities (error / warning / info) per rule | see YAML | My choice, not from a source. Please review |
| checklist: "Latvian and English abstracts say the same thing" | included | (assumed) |

## C. Taken from the RTU slides (please check my wording)

The slide PDFs are **not yet in `docs/sources/`**. The page references below come
from BUILD_PROMPT, not from my own reading of the slides. Once you add the PDFs I'll
check every `rule_text` against them.

| Rule | guideline_ref |
|---|---|
| REF-AI-01 AI-tool reference format | ai-slides p.4 |
| STRUCT-05 "Tools used in writing this thesis" paragraph | ai-slides p.5 |
| CITE-04 quotation without a reference | plag-slides p.6 |
| CITE-05 long literature-review paragraph without references | plag-slides p.5 |
| REF-04 secondary sources (Wikipedia, slides) | plag-slides p.5 |
| `date_format` DD.MM.YYYY. | ai-slides p.4 |
