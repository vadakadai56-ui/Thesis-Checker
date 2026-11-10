"""Small helpers for changing Word XML safely.

Word is strict about the ORDER of elements inside <w:pPr>, <w:rPr>, <w:sectPr> and
<w:settings>; a file with elements in the wrong order is reported as damaged.
python-docx's `get_or_add_…()` methods insert in the right place; for the few
elements it doesn't cover, `insert_ordered()` uses the order from the OOXML schema.
"""

from __future__ import annotations

import re
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

# Elements that must come AFTER the one we insert (OOXML schema order).
_SECTPR_AFTER_PGNUMTYPE = [
    "w:cols", "w:formProt", "w:vAlign", "w:noEndnote", "w:titlePg", "w:textDirection",
    "w:bidi", "w:rtlGutter", "w:docGrid", "w:printerSettings", "w:sectPrChange",
]  # fmt: skip
_SETTINGS_AFTER_MIRROR = [
    "w:alignBordersAndEdges", "w:bordersDoNotSurroundHeader", "w:bordersDoNotSurroundFooter",
    "w:gutterAtTop", "w:hideSpellingErrors", "w:hideGrammaticalErrors", "w:activeWritingStyle",
    "w:proofState", "w:formsDesign", "w:attachedTemplate", "w:linkStyles",
    "w:stylePaneFormatFilter", "w:stylePaneSortMethod", "w:documentType", "w:mailMerge",
    "w:revisionView", "w:trackRevisions", "w:doNotTrackMoves", "w:doNotTrackFormatting",
    "w:documentProtection", "w:autoFormatOverride", "w:styleLockTheme", "w:styleLockQFSet",
    "w:defaultTabStop", "w:autoHyphenation", "w:consecutiveHyphenLimit", "w:hyphenationZone",
    "w:doNotHyphenateCaps", "w:showEnvelope", "w:summaryLength", "w:clickAndTypeStyle",
    "w:defaultTableStyle", "w:evenAndOddHeaders", "w:bookFoldRevPrinting", "w:bookFoldPrinting",
    "w:bookFoldPrintingSheets", "w:drawingGridHorizontalSpacing",
    "w:drawingGridVerticalSpacing", "w:displayHorizontalDrawingGridEvery",
    "w:displayVerticalDrawingGridEvery", "w:doNotUseMarginsForDrawingGridOrigin",
    "w:drawingGridHorizontalOrigin", "w:drawingGridVerticalOrigin", "w:doNotShadeFormData",
    "w:noPunctuationKerning", "w:characterSpacingControl", "w:printTwoOnOne",
    "w:strictFirstAndLastChars", "w:noLineBreaksAfter", "w:noLineBreaksBefore",
    "w:savePreviewPicture", "w:doNotValidateAgainstSchema", "w:saveInvalidXml",
    "w:ignoreMixedContent", "w:alwaysShowPlaceholderText", "w:doNotDemarcateInvalidXml",
    "w:saveXmlDataOnly", "w:useXSLTWhenSaving", "w:saveThroughXslt", "w:showXMLTags",
    "w:alwaysMergeEmptyNamespace", "w:updateFields", "w:hdrShapeDefaults", "w:footnotePr",
    "w:endnotePr", "w:compat", "w:docVars", "w:rsids", "m:mathPr", "w:attachedSchema",
    "w:themeFontLang", "w:clrSchemeMapping", "w:doNotIncludeSubdocsInStats",
    "w:doNotAutoCompressPictures", "w:forceUpgrade", "w:captions", "w:readModeInkLockDown",
    "w:smartTagType", "sl:schemaLibrary", "w:shapeDefaults", "w:doNotEmbedSmartTags",
    "w:decimalSymbol", "w:listSeparator",
]  # fmt: skip


# The full order list for settings, starting with the elements before mirrorMargins.
SETTINGS_ORDER = [
    "w:writeProtection", "w:view", "w:zoom", "w:removePersonalInformation",
    "w:removeDateAndTime", "w:doNotDisplayPageBoundaries", "w:displayBackgroundShape",
    "w:printPostScriptOverText", "w:printFractionalCharacterWidth", "w:printFormsData",
    "w:embedTrueTypeFonts", "w:embedSystemFonts", "w:saveSubsetFonts", "w:saveFormsData",
    "w:mirrorMargins", *_SETTINGS_AFTER_MIRROR,
]  # fmt: skip


def _successors(order: list[str], tag: str) -> list[str]:
    return order[order.index(tag) + 1 :] if tag in order else []


def insert_ordered(parent: Any, tag: str, order: list[str]) -> Any:
    """Return child `tag` of `parent`, creating it at its schema position if missing."""
    existing = parent.find(qn(tag))
    if existing is not None:
        return existing
    element = OxmlElement(tag)
    successors = {qn(t) for t in _successors(order, tag) if t.startswith("w:")}
    for i, child in enumerate(parent):
        if child.tag in successors:
            parent.insert(i, element)
            return element
    parent.append(element)
    return element


def set_setting(settings: Any, tag: str, on: bool) -> bool:
    """Switch an on/off document setting (e.g. w:updateFields). Returns True if changed."""
    existing = settings.find(qn(tag))
    if on:
        if existing is not None and existing.get(qn("w:val")) in (None, "1", "true", "on"):
            return False
        element = insert_ordered(settings, tag, SETTINGS_ORDER)
        element.set(qn("w:val"), "true")
        return True
    if existing is None:
        return False
    settings.remove(existing)
    return True


def pg_num_type(sect_pr: Any) -> Any:
    return insert_ordered(sect_pr, "w:pgNumType", ["w:pgNumType", *_SECTPR_AFTER_PGNUMTYPE])


def set_attrs(element: Any, **values: Any) -> None:
    """Set w:-attributes; a value of None removes the attribute."""
    for name, value in values.items():
        key = qn(f"w:{name}")
        if value is None:
            element.attrib.pop(key, None)
        else:
            element.set(key, str(value))


def remove_attrs(element: Any, *names: str) -> int:
    """Remove w:-attributes; returns how many were present."""
    count = 0
    for name in names:
        if element.attrib.pop(qn(f"w:{name}"), None) is not None:
            count += 1
    return count


def drop_if_empty(element: Any) -> None:
    """Remove an element that has no attributes and no children left."""
    if element is not None and not len(element) and not element.attrib:
        element.getparent().remove(element)


def remove_children(parent: Any, *tags: str) -> int:
    """Remove all direct children with these tags (e.g. "w:sz"); returns the count."""
    count = 0
    if parent is None:
        return 0
    for tag in tags:
        for child in parent.findall(qn(tag)):
            parent.remove(child)
            count += 1
    return count


def set_toggle(rpr: Any, tag: str, on: bool) -> None:
    """Set an on/off run property such as w:b or w:caps on an <w:rPr>."""
    element = getattr(rpr, f"get_or_add_{tag.split(':')[1]}")()
    if on:
        element.attrib.pop(qn("w:val"), None)
    else:
        element.set(qn("w:val"), "0")


def set_size(rpr: Any, half_points: int) -> None:
    """Set w:sz and w:szCs (the size for complex scripts) together."""
    rpr.get_or_add_sz().set(qn("w:val"), str(half_points))
    sz_cs = rpr.find(qn("w:szCs"))
    if sz_cs is None:
        sz_cs = OxmlElement("w:szCs")
        rpr.find(qn("w:sz")).addnext(sz_cs)
    sz_cs.set(qn("w:val"), str(half_points))


def set_font(rpr: Any, name: str) -> None:
    """Set the Latin fonts and drop theme-font links that would override them."""
    rfonts = rpr.get_or_add_rFonts()
    remove_attrs(rfonts, "asciiTheme", "hAnsiTheme")
    set_attrs(rfonts, ascii=name, hAnsi=name)


# ------------------------------------------------------------------ fields

_PAGE_INSTR = re.compile(r"^\s*PAGE(\s|\\|$)", re.IGNORECASE)


def _instr_of_simple(el: Any) -> str:
    return el.get(qn("w:instr")) or ""


def has_page_field(p_el: Any) -> bool:
    if any(_PAGE_INSTR.match(_instr_of_simple(f)) for f in p_el.iter(qn("w:fldSimple"))):
        return True
    return any(_PAGE_INSTR.match(t.text or "") for t in p_el.iter(qn("w:instrText")))


def remove_page_fields(p_el: Any) -> int:
    """Remove PAGE fields (the whole begin…end run range) from a paragraph."""
    removed = 0
    for simple in list(p_el.iter(qn("w:fldSimple"))):
        if _PAGE_INSTR.match(_instr_of_simple(simple)):
            simple.getparent().remove(simple)
            removed += 1
    runs = list(p_el.iter(qn("w:r")))
    i = 0
    while i < len(runs):
        begin = runs[i].find(qn("w:fldChar"))
        if begin is not None and begin.get(qn("w:fldCharType")) == "begin":
            depth, j, instr = 0, i, ""
            while j < len(runs):
                for child in runs[j]:
                    if child.tag == qn("w:fldChar"):
                        kind = child.get(qn("w:fldCharType"))
                        depth += 1 if kind == "begin" else -1 if kind == "end" else 0
                    elif child.tag == qn("w:instrText") and depth == 1:
                        instr += child.text or ""
                if depth == 0:
                    break
                j += 1
            if _PAGE_INSTR.match(instr):
                for run in runs[i : j + 1]:
                    run.getparent().remove(run)
                removed += 1
            i = j + 1
        else:
            i += 1
    return removed


def append_field(p_el: Any, instruction: str, result: str = "1") -> None:
    """Append a complex field ({ PAGE } etc.) at the end of a paragraph element."""

    def run(child: Any) -> None:
        r = OxmlElement("w:r")
        r.append(child)
        p_el.append(r)

    def fld(kind: str) -> Any:
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), kind)
        return el

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    text = OxmlElement("w:t")
    text.text = result
    for child in (fld("begin"), instr, fld("separate"), text, fld("end")):
        run(child)
