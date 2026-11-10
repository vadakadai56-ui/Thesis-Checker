"""Importing this package registers every rule module with the registry."""

from . import (  # noqa: F401  (imported for their @rule side effect)
    ai_disclosure,
    citations,
    consistency,
    figures_tables,
    headings,
    page_numbers,
    page_setup,
    structure,
    text,
    title_page,
    toc,
)
from .registry import RuleContext, SkipRule, get_rule, registered_rule_ids, rule

__all__ = ["RuleContext", "SkipRule", "get_rule", "registered_rule_ids", "rule"]
