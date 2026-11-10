"""Generate the test documents in engine/tests/samples/.

    python tools/make_samples.py            (run from engine/)

* clean.docx    – a short, SYNTHETIC demo thesis that follows the DEMO profile.
* <RULE-ID>.docx – the same document with exactly ONE rule broken.

The text is invented ("Demo Student", a made-up topic) — never a real thesis.
Output is byte-for-byte reproducible (fixed timestamps), so a test can verify the
committed samples are up to date.
"""

from __future__ import annotations

import io
import sys
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import docx
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

ENGINE_DIR = Path(__file__).resolve().parents[1]
SAMPLES_DIR = ENGINE_DIR / "tests" / "samples"
FIXED_TIME = datetime(2026, 1, 1, 12, 0, 0)

# The DEMO profile's values (engine/profiles/demo.yaml).
DEMO_MARGINS_CM = {"top": 2.0, "bottom": 2.0, "left": 3.0, "right": 2.0}
DEMO_FONT = "Times New Roman"
DEMO_SIZE_PT = 12

BODY = [
    "Small software teams often decide how to test their code without measuring "
    "the effect of that decision (Example, 2024). This demo thesis describes a "
    "made-up study used only to test the ThesisCheck engine.",
    "The aim of the work is to compare two imaginary testing approaches and to "
    "describe the results in a clear and repeatable way.",
]
THEORY = [
    "Earlier imaginary studies describe unit tests, integration tests and manual "
    "review as complementary activities (Sample and Person, 2023).",
    "Each approach finds a different kind of defect, so teams usually combine "
    "them instead of choosing only one.",
]
METHOD = [
    "The study uses invented data from twelve fictional projects. Every project "
    "is described by its size, its number of tests and its number of defects.",
]
CONCLUSIONS = [
    "The invented results suggest that combining approaches works best. Because "
    "the data is made up, no real conclusion can be drawn from this document.",
]
REFERENCES = [
    "Example, A. (2024). An invented article about software testing. Demo Journal, 1(1), 1–10.",
    "Sample, B. and Person, C. (2023). A made-up book on code review. Demo Press.",
]

# Each block is (kind, text). kind = "title", "line", "h1".."h3", "p".
Blocks = list[tuple[str, str]]


def clean_blocks() -> Blocks:
    blocks: Blocks = [
        ("title", "Measuring Testing Practices in Small Teams"),
        ("line", "Demo Student"),
        ("line", "Bachelor thesis (synthetic sample)"),
        ("line", "Demo City 2026"),
        ("h1", "Introduction"),
        *[("p", t) for t in BODY],
        ("h1", "1 Theory"),
        *[("p", t) for t in THEORY],
        ("h2", "1.1 Research method"),
        *[("p", t) for t in METHOD],
        ("h3", "1.1.1 Data set"),
        ("p", METHOD[0]),
        ("h1", "Conclusions"),
        *[("p", t) for t in CONCLUSIONS],
        ("h1", "References"),
        *[("p", t) for t in REFERENCES],
    ]
    return blocks


def _set_style_font(style, name: str, size_pt: float) -> None:
    """Set a style's font and remove theme-font links, so the font name really applies."""
    style.font.name = name
    style.font.size = Pt(size_pt)
    rfonts = style.element.get_or_add_rPr().find(qn("w:rFonts"))
    for attr in ("w:asciiTheme", "w:hAnsiTheme"):
        if rfonts is not None and rfonts.get(qn(attr)) is not None:
            del rfonts.attrib[qn(attr)]


def build_document(blocks: Blocks, *, normal_font: str | None = DEMO_FONT) -> docx.Document:
    doc = docx.Document()
    if normal_font is not None:
        _set_style_font(doc.styles["Normal"], normal_font, DEMO_SIZE_PT)

    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)  # A4
    section.top_margin = Cm(DEMO_MARGINS_CM["top"])
    section.bottom_margin = Cm(DEMO_MARGINS_CM["bottom"])
    section.left_margin = Cm(DEMO_MARGINS_CM["left"])
    section.right_margin = Cm(DEMO_MARGINS_CM["right"])

    for kind, text in blocks:
        if kind == "title":
            doc.add_paragraph(text, style="Title")
        elif kind == "line":
            doc.add_paragraph(text)
        elif kind.startswith("h"):
            doc.add_heading(text, level=int(kind[1]))
        else:
            doc.add_paragraph(text)

    props = doc.core_properties
    props.author = "ThesisCheck sample generator"
    props.title = "Synthetic demo thesis"
    props.created = props.modified = FIXED_TIME
    props.last_modified_by = "ThesisCheck sample generator"
    props.revision = 1
    return doc


def to_bytes(doc: docx.Document) -> bytes:
    """Save, then rewrite the ZIP with fixed timestamps so output is reproducible."""
    raw = io.BytesIO()
    doc.save(raw)
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(raw.getvalue())) as src,
        zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for info in src.infolist():
            fixed = zipfile.ZipInfo(info.filename, date_time=FIXED_TIME.timetuple()[:6])
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = 0o644 << 16
            dst.writestr(fixed, src.read(info.filename))
    return out.getvalue()


# --------------------------------------------------------- one broken rule each


def _body_paragraph(doc: docx.Document, starts_with: str):
    return next(p for p in doc.paragraphs if p.text.startswith(starts_with))


def make_clean() -> docx.Document:
    return build_document(clean_blocks())


def make_page_01() -> docx.Document:
    doc = make_clean()
    doc.sections[0].left_margin = Cm(2.5)  # demo wants 3.0 cm
    return doc


def make_page_02() -> docx.Document:
    doc = make_clean()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21.59), Cm(27.94)  # US Letter
    return doc


def make_text_01() -> docx.Document:
    doc = make_clean()
    para = _body_paragraph(doc, "The aim of the work")
    para.add_run(" Extra sentence typed in another font.").font.name = "Arial"
    return doc


def make_text_02() -> docx.Document:
    doc = make_clean()
    para = _body_paragraph(doc, "The aim of the work")
    para.add_run(" Extra sentence in a bigger size.").font.size = Pt(14)
    return doc


def make_head_03() -> docx.Document:
    blocks = [("h3", t) if t == "1.1 Research method" else (k, t) for k, t in clean_blocks()]
    return build_document(blocks)


SAMPLES: dict[str, Callable[[], docx.Document]] = {
    "clean": make_clean,
    "PAGE-01": make_page_01,
    "PAGE-02": make_page_02,
    "TEXT-01": make_text_01,
    "TEXT-02": make_text_02,
    "HEAD-03": make_head_03,
}


# ------------------------------------------- extra documents built inside tests


def make_landscape_rotated() -> docx.Document:
    """Clean doc + a second, landscape section whose margins are rotated (allowed)."""
    doc = make_clean()
    new = doc.add_section()
    new.orientation = WD_ORIENT.LANDSCAPE
    new.page_width, new.page_height = Cm(29.7), Cm(21)
    # Rotated clockwise: top=left(3), right=top(2), bottom=right(2), left=bottom(2).
    new.top_margin, new.right_margin = Cm(3.0), Cm(2.0)
    new.bottom_margin, new.left_margin = Cm(2.0), Cm(2.0)
    doc.add_paragraph("A wide table would go on this landscape page.")
    return doc


def make_theme_font_only() -> docx.Document:
    """Normal style has NO font of its own, so the theme's body font applies."""
    return build_document(clean_blocks(), normal_font=None)


def generate(out_dir: Path = SAMPLES_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, factory in SAMPLES.items():
        path = out_dir / f"{name}.docx"
        path.write_bytes(to_bytes(factory()))
        written.append(path)
    return written


if __name__ == "__main__":
    for p in generate():
        print(f"wrote {p.relative_to(ENGINE_DIR)}")
    sys.exit(0)
