"""Figures and tables: caption present with the right label (FIG-01/TAB-01), numbered
in order per chapter (-02), on the right side (-03), mentioned in the text (-04),
and lists of figures/tables match the captions (LIST-01).

The caption format comes from the profile's `captions` section, e.g.
    figure: {label: "Fig.", per_chapter: true, position: below}
    table:  {label: "Table", per_chapter: true, position: above}
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..document_view import ParagraphView
from ..model import Location
from .registry import RuleContext, SkipRule, paragraph_location, rule
from .toc import _entry_parts

GENERIC_ROOTS = {"figure": ["fig", "att", "attēl"], "table": ["tab", "tabul"]}
_MENTION_DISTANCE = 25  # characters between a number and the word "Fig."/"Table"


@dataclass(frozen=True)
class Caption:
    paragraph: ParagraphView
    label: str
    number: str
    side: str  # above | below | same


@dataclass(frozen=True)
class Item:
    kind: str  # figure | table
    anchor: ParagraphView  # the image paragraph, or the first cell of the table
    before: int | None  # paragraph index just before the item
    after: int | None  # paragraph index just after the item
    caption: Caption | None


def _config(ctx: RuleContext, kind: str) -> dict:
    cfg = ctx.setting("captions", kind)
    if not isinstance(cfg, dict) or not cfg.get("label"):
        raise SkipRule(f"The profile has no {kind} caption format.")
    return cfg


def _roots(cfg: dict, kind: str) -> list[str]:
    roots = {cfg["label"].rstrip(".").casefold(), *GENERIC_ROOTS[kind]}
    return sorted((re.escape(r) for r in roots if r), key=len, reverse=True)


def caption_match(text: str, cfg: dict, kind: str) -> tuple[str, str] | None:
    """('Fig.', '2.1') if `text` is a caption of this kind, else None."""
    roots = "|".join(_roots(cfg, kind))
    clean = " ".join(text.split())
    match = re.match(rf"^(?P<label>(?:{roots})\w*\.?)\s*(?P<num>\d+(?:\.\d+)*)", clean, re.I)
    if not match:
        match = re.match(rf"^(?P<num>\d+(?:\.\d+)*)\.?\s*(?P<label>(?:{roots})\w*\.?)", clean, re.I)
    if not match:
        return None
    return match.group("label"), match.group("num").rstrip(".")


def _scan(ctx: RuleContext, start: int | None, step: int, cfg: dict, kind: str):
    """Look up to 3 paragraphs away (one direction) for a caption of this kind."""
    if start is None:
        return None
    paragraphs = ctx.view.paragraphs
    i, seen = start, 0
    while 0 <= i < len(paragraphs) and seen < 3:
        p = paragraphs[i]
        i += step
        if p.is_empty and not p.has_image:
            continue
        seen += 1
        found = caption_match(p.text, cfg, kind)
        if found and p.is_caption_like:  # "Fig. 1.1 shows …" is a sentence, not a caption
            return p, found
        if p.heading_level is not None or p.has_image or p.in_table:
            return None
        if p.is_body and not p.is_caption_like and len(p.text.split()) > 25:
            return None
    return None


def _find_caption(ctx: RuleContext, item: Item, cfg: dict) -> Caption | None:
    if item.kind == "figure":
        same = caption_match(item.anchor.text, cfg, item.kind)
        if same:
            return Caption(item.anchor, same[0], same[1], "same")
    preferred = cfg.get("position", "below" if item.kind == "figure" else "above")
    order = ["below", "above"] if preferred == "below" else ["above", "below"]
    for side in order:
        start, step = (item.after, 1) if side == "below" else (item.before, -1)
        found = _scan(ctx, start, step, cfg, item.kind)
        if found:
            return Caption(found[0], found[1][0], found[1][1], side)
    return None


def items(ctx: RuleContext, kind: str) -> list[Item]:
    cfg = _config(ctx, kind)
    result: list[Item] = []
    view = ctx.view
    if kind == "figure":
        for p in view.paragraphs:
            if p.has_image and not p.in_table and not ctx.regions.contains("title_page", p.index):
                item = Item(kind, p, p.index - 1 if p.index else None, p.index + 1, None)
                result.append(Item(kind, p, item.before, item.after, _find_caption(ctx, item, cfg)))
    else:
        for t in view.tables:
            anchor = view.paragraphs[t.first_paragraph]
            if ctx.regions.contains("title_page", anchor.index):
                continue
            item = Item(kind, anchor, t.before_paragraph, t.after_paragraph, None)
            result.append(
                Item(kind, anchor, item.before, item.after, _find_caption(ctx, item, cfg))
            )
    if not result:
        raise SkipRule(f"No {kind}s found.")
    return result


def _where(item: Item) -> Location:
    return paragraph_location(item.caption.paragraph if item.caption else item.anchor)


# ---------------------------------------------------------------- shared checks


def check_caption_present(ctx: RuleContext, kind: str) -> None:
    cfg = _config(ctx, kind)
    for item in items(ctx, kind):
        if item.caption is None:
            ctx.report(
                message=f"This {kind} has no caption.",
                location=_where(item),
                expected=f"a caption like “{cfg['label']} 1.1”",
                found="no caption",
            )
        elif item.caption.label.casefold() != cfg["label"].casefold():
            ctx.report(
                message=(
                    f"The {kind} caption uses “{item.caption.label}” instead of “{cfg['label']}”."
                ),
                location=_where(item),
                expected=cfg["label"],
                found=item.caption.label,
            )


def check_numbering(ctx: RuleContext, kind: str) -> None:
    cfg = _config(ctx, kind)
    per_chapter = cfg.get("per_chapter", True)
    counters: dict[object, int] = {}
    for item in items(ctx, kind):
        if item.caption is None or ctx.regions.after_marker("appendixes", item.anchor.index):
            continue
        chapter = ctx.regions.chapter_of(item.anchor.index)
        group = chapter.index if (per_chapter and chapter) else "all"
        counters[group] = counters.get(group, 0) + 1
        n = counters[group]
        if per_chapter:
            chapter_no = (chapter.heading_number or "").split(".")[0] if chapter else ""
            prefix = chapter_no or item.caption.number.split(".")[0]
            expected = f"{prefix}.{n}"
        else:
            expected = str(n)
        if item.caption.number != expected:
            ctx.report(
                message=f"{cfg['label']} {item.caption.number} should be numbered {expected}.",
                location=_where(item),
                expected=expected,
                found=item.caption.number,
            )


def check_position(ctx: RuleContext, kind: str) -> None:
    cfg = _config(ctx, kind)
    want = cfg.get("position", "below" if kind == "figure" else "above")
    for item in items(ctx, kind):
        if item.caption is not None and item.caption.side not in (want, "same"):
            ctx.report(
                message=(
                    f"The {kind} caption is {item.caption.side} the {kind}; it should be {want}."
                ),
                location=_where(item),
                expected=want,
                found=item.caption.side,
            )


def check_mentioned(ctx: RuleContext, kind: str) -> None:
    cfg = _config(ctx, kind)
    roots = "|".join(_roots(cfg, kind))
    texts = [
        p.clean_text
        for p in ctx.view.paragraphs
        if (p.is_body or p.numbering) and not p.is_caption_like
    ]
    for item in items(ctx, kind):
        if item.caption is None or ctx.regions.after_marker("appendixes", item.anchor.index):
            continue
        number = re.escape(item.caption.number)
        near = (
            rf"(?:(?:{roots})\w*\.?[^\d]{{0,{_MENTION_DISTANCE}}}(?<![\d.]){number}(?!\.?\d))"
            rf"|(?:(?<![\d.]){number}\.?[^\d]{{0,{_MENTION_DISTANCE}}}(?:{roots}))"
        )
        if not any(re.search(near, t, re.IGNORECASE) for t in texts):
            ctx.report(
                message=f"{cfg['label']} {item.caption.number} is never mentioned in the text.",
                location=_where(item),
                expected=f"a mention like “see {cfg['label']} {item.caption.number}”",
                found="not mentioned",
            )


_HOW_CAPTION = "Insert a caption with References → Insert Caption, using the required label."
_HOW_NUMBER = "Use Insert Caption (with chapter numbering) so Word numbers captions for you."


@rule("FIG-01", title="Figure caption", how_to_fix=_HOW_CAPTION)
def fig01(ctx: RuleContext) -> None:
    check_caption_present(ctx, "figure")


@rule("FIG-02", title="Figure numbering", how_to_fix=_HOW_NUMBER)
def fig02(ctx: RuleContext) -> None:
    check_numbering(ctx, "figure")


@rule("FIG-03", title="Figure caption position", how_to_fix="Move the caption below the figure.")
def fig03(ctx: RuleContext) -> None:
    check_position(ctx, "figure")


@rule(
    "FIG-04",
    title="Figure mentioned in text",
    how_to_fix="Refer to the figure in the text, e.g. “(see Fig. 2.1)”.",
)
def fig04(ctx: RuleContext) -> None:
    check_mentioned(ctx, "figure")


@rule("TAB-01", title="Table caption", how_to_fix=_HOW_CAPTION)
def tab01(ctx: RuleContext) -> None:
    check_caption_present(ctx, "table")


@rule("TAB-02", title="Table numbering", how_to_fix=_HOW_NUMBER)
def tab02(ctx: RuleContext) -> None:
    check_numbering(ctx, "table")


@rule(
    "TAB-03",
    title="Table caption position",
    how_to_fix="Move the table number and name above the table.",
)
def tab03(ctx: RuleContext) -> None:
    check_position(ctx, "table")


@rule(
    "TAB-04",
    title="Table mentioned in text",
    how_to_fix="Refer to the table in the text, e.g. “(see Table 2.1)”.",
)
def tab04(ctx: RuleContext) -> None:
    check_mentioned(ctx, "table")


@rule(
    "LIST-01",
    title="List of figures/tables",
    how_to_fix="References → Insert Table of Figures; right-click it → Update Field to refresh.",
)
def check_lists(ctx: RuleContext) -> None:
    view = ctx.view
    list_fields = [f for f in view.fields_named("TOC") if re.search(r"\\[ca]\b", f.instruction)]
    indices = {i for f in list_fields for i in f.paragraph_indices}
    indices |= {
        p.index for p in view.paragraphs if (p.style_name or "").casefold() == "table of figures"
    }
    entries = [view.paragraphs[i] for i in sorted(indices) if not view.paragraphs[i].is_empty]
    if not entries:
        if ctx.expected.get("required"):
            ctx.report(
                message="There is no list of figures/tables.",
                location=Location(part="body"),
                expected="a list of figures/tables",
                found="none",
            )
        return
    captions: dict[str, str] = {}
    for kind in ("figure", "table"):
        try:
            found = items(ctx, kind)
        except SkipRule:
            continue
        for item in found:
            if item.caption:
                captions[" ".join(item.caption.paragraph.text.split()).casefold()] = kind
    listed = set()
    for p in entries:
        text, _ = _entry_parts(p)
        listed.add(text)
        if text not in captions:
            ctx.report(
                message="This list entry matches no caption in the text.",
                location=paragraph_location(p),
                expected="an entry for an existing caption",
                found=p.snippet,
            )
    # Only expect captions of the kinds that are listed (a list of figures alone
    # doesn't need to contain the tables).
    listed_kinds = {captions[t] for t in listed if t in captions}
    for text, kind in captions.items():
        if kind in listed_kinds and text not in listed:
            ctx.report(
                message="This caption is missing from the list of figures/tables.",
                location=Location(part="body", snippet=text[:60]),
                expected="listed",
                found="not listed",
            )
