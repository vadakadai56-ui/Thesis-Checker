"""Importing this package registers every rule module with the registry."""

from . import headings, page_setup, text  # noqa: F401  (imported for their @rule side effect)
from .registry import RuleContext, SkipRule, get_rule, registered_rule_ids, rule

__all__ = ["RuleContext", "SkipRule", "get_rule", "registered_rule_ids", "rule"]
