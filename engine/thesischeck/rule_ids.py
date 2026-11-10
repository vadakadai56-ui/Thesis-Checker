"""The complete list of rule IDs (BUILD_PROMPT §5) and the category each belongs to.

Profiles may only use IDs from this list (the schema checks it), so a typo such as
"PAGE-1" is caught at build time instead of silently disabling a rule.
"""

from __future__ import annotations

# Category slug -> label shown in the UI (same order as BUILD_PROMPT §4b).
CATEGORIES: dict[str, str] = {
    "page_setup": "Page setup",
    "text": "Text",
    "headings": "Headings",
    "page_numbers": "Page numbers",
    "structure": "Structure",
    "contents": "Contents",
    "figures_tables": "Figures & tables",
    "citations": "Citations & references",
    "ai_disclosure": "AI disclosure",
    "consistency": "Consistency",
    "title_page": "Title page",
}


def _ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{n:02d}" for n in range(1, count + 1)]


RULE_CATEGORIES: dict[str, str] = {
    **dict.fromkeys(_ids("PAGE", 4), "page_setup"),
    **dict.fromkeys(_ids("TEXT", 8), "text"),
    **dict.fromkeys(_ids("HEAD", 6), "headings"),
    **dict.fromkeys(_ids("PGNUM", 3), "page_numbers"),
    **dict.fromkeys(_ids("STRUCT", 4), "structure"),
    "STRUCT-05": "ai_disclosure",
    **dict.fromkeys(_ids("TOC", 3), "contents"),
    **dict.fromkeys(_ids("FIG", 4), "figures_tables"),
    **dict.fromkeys(_ids("TAB", 4), "figures_tables"),
    "LIST-01": "figures_tables",
    **dict.fromkeys(_ids("CITE", 5), "citations"),
    **dict.fromkeys(_ids("REF", 4), "citations"),
    "REF-AI-01": "ai_disclosure",
    **dict.fromkeys(_ids("CONS", 3), "consistency"),
    **dict.fromkeys(_ids("TITLE", 2), "title_page"),
}

ALL_RULE_IDS: tuple[str, ...] = tuple(RULE_CATEGORIES)
