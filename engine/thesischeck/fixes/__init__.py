"""Fix functions (BUILD_PROMPT §4d), one per auto-fixable rule.

They are registered with @fixer("RULE-ID") and only ever called by fixer.py, on a
copy of the document. Each changes FORMATTING ONLY and returns how many changes
it made.
"""

from . import headings, page_numbers, page_setup, references, text  # noqa: F401
