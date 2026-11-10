# RTU profile — values waiting for you

File: `engine/profiles/rtu-fcsite-bachelor.yaml` (status: **draft**).

Rules whose value is `TODO` are **not checked**. The app lists them as "not yet
checked", so nothing is guessed.

## Filled from the RTU thesis template (2024)

These values were read straight from `RTU_k_thesis_template_2024.dotx`: its styles,
page setup and footers, and the instructions written inside it. Each rule's
`guideline_ref` says where. A test checks that the template passes the profile with
0 findings, and that the profile's values match the template's styles.

| Area | Value | Where in the template |
|---|---|---|
| Paper | A4 | page setup |
| Margins | top/bottom 2.54 cm, left/right 3.18 cm | page setup, all sections ⚠ see below |
| Gutter / mirror margins | none | page setup |
| Body text | Times New Roman 12 pt, 1.5 lines, justified, 0 pt before/after, first line 1.27 cm | styles Normal + Text |
| Heading 1 | 14 pt bold, ALL CAPS (style), centred, 12 pt after, new page | Heading 1 / Level-1-heading |
| Heading 2 | 14 pt bold, centred, 12 pt before/after | Heading 2 / Level-2-heading |
| Heading 3 | 12 pt bold, centred, 12 pt before/after | Heading 3 / Level-3-heading |
| Numbering | 1. / 1.1. / 1.1.1.; unnumbered: Abstract, Anotācija, Contents, Introduction, Results and conclusions, References, Appendixes | headings + TOC |
| Page numbers | bottom centre, Arabic; title page has no number and isn't counted; numbering starts at 1 on the Assessment Sheet | footers, section settings |
| Structure | title page → Work Performance and Assessment Sheet → ABSTRACT → ANOTĀCIJA → TABLE OF CONTENTS → INTRODUCTION → chapters → RESULTS AND CONCLUSIONS → LIST OF REFERENCES → (APPENDIXES) | document |
| Abstract | 3–5 key words, at most 1 page; Anotācija is its Latvian translation | ABSTRACT page |
| Section lengths | Introduction 1–2 pages; Results and conclusions 1–3 pages | text of those pages |
| Figures | "Fig. 2.1. Title" below the figure, centred, bold, numbered per chapter | example figure |
| Tables | "Table 2.1" right-aligned bold, then the name centred bold, both above the table | example table |
| Formulas | numbered "(2.1.)" at the right | example formula |
| References | style Info-source: 1 cm hanging indent | style Info-source |
| Title page | university, faculty, institute, student name, programme, student ID, title, type of work, scientific adviser, "RIGA <year>" | title page |
| Not body text | Code (Arial Narrow 11 pt), Table-explanation (10 pt), Appendices-heading, Formulas | list of styles |

### ⚠ Please confirm

1. **Margins.** 2.54 / 2.54 / 3.18 / 3.18 cm are exactly Word's built-in "Normal"
   margins. Is that RTU's real requirement, or did the template just keep Word's
   default? Many guidelines use something like left 3 cm / right 2 cm.
2. **One template for all levels.** The template covers bachelor, master, diploma
   project and qualification paper. Should there be one profile for all, rather
   than separate bachelor/master files?
3. **Commit the template?** It's saved only locally (`engine/tests/private/`,
   git-ignored). The repo is public, so I didn't commit RTU's file. Should it go in
   `docs/sources/`?

### Found by checking the template itself (stage 2)

Run on the untouched template, the RTU profile reports 7 findings. Two of them
may be problems in the template rather than in ThesisCheck:

4. **No page numbers on the last pages.** The template's last section (LIST OF
   REFERENCES + APPENDIXES) has an empty footer, so those pages have no number
   (PGNUM-02). Is that intended, or a template mistake?
5. **Formula explanation lines.** The "where Qg – …" lines under the example
   formula have no first-line indent (style Normal, not Text), so TEXT-06 flags
   them. Should lines like that be exempt?

The other findings are expected for an unfilled template: `<…>` placeholders and
no year on the title page, and no "Tools used in writing this thesis" paragraph.

### Latvian wording (assumed): please confirm

To recognise a Latvian-language thesis, the profile also accepts these headings:
SATURS, IEVADS, REZULTĀTI UN SECINĀJUMI / SECINĀJUMI, IZMANTOTĀS INFORMĀCIJAS
AVOTI / INFORMĀCIJAS AVOTU SARAKSTS, PIELIKUMI, plus "Darba izpildes un
novērtējuma lapa". For the title page it accepts "Rīgas Tehniskā universitāte",
"fakultāte", "institūts", "studiju programma", "apliecības Nr.", "bakalaura darbs",
"maģistra darbs", "zinātniskais vadītājs" and "RĪGA <year>". These are my
assumptions, not from a source.

## Still TODO — not in the template or the slides

| Rule | What I need |
|---|---|
| (profile) `programme` | Programme name(s) |
| PAGE-03 | Are landscape pages allowed, and where? |
| TEXT-07 | Should direct formatting be flagged, and from what % of a paragraph? |
| TEXT-08 | Flag empty paragraphs used for spacing? (The template uses some itself.) |
| STRUCT-04 | Total thesis length (pages or words) |
| FIG-04, TAB-04 | Must every figure/table be referred to in the text? |
| LIST-01 | Are lists of figures/tables required? |
| CITE-01, CITE-02, REF-01 | The reference format. The template's examples look like ISO 690 ("Available from: …"). Which standard? |
| CONS-01..03 | Do you want these consistency checks for RTU? |
| `structure.keyword_labels` | How the key words are introduced in the Abstract (e.g. "Key words:" / "Atslēgas vārdi:") |
| `structure.literature_review_headings` | Which chapters are literature reviews (for CITE-05) |
| `ai_disclosure.heading_phrases.lv` | Latvian wording of "Tools used in writing this thesis" |

## Assumed defaults — confirm or change

| Item | Current value |
|---|---|
| CITE-03 citation style | author–date `(Author, 2026)`. The template has no in-text example; ai-slides p.4 shows "(OpenAI, 2026)". Or numeric `[1]`? |
| CITE-05 threshold | 120 words |
| REF-02 reference order | alphabetical (the template's 3 examples are alphabetical) |
| degree level | bachelor |
| severities (error / warning / info) | my choice. Please review |

## From the RTU slides (please check my wording)

The slide PDFs are **not yet in `docs/sources/`**. These page references come from
BUILD_PROMPT, not from my own reading.

| Rule | guideline_ref |
|---|---|
| REF-AI-01 AI-tool reference format | ai-slides p.4 |
| STRUCT-05 "Tools used in writing this thesis" | ai-slides p.5 |
| CITE-04 quotation without a reference | plag-slides p.6 |
| CITE-05 long paragraph without references | plag-slides p.5 |
| REF-04 secondary sources | plag-slides p.5 |
