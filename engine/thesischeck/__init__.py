"""ThesisCheck rules engine — plain Python, no browser code (BUILD_PROMPT §3, §7).

Public API: check(), fix(), annotate(), score().
"""

from . import fixer  # noqa: F401  (registers fix functions, so findings know they're fixable)
from .api import ENGINE_VERSION, annotate, check, fix, score
from .model import EngineError

__all__ = ["ENGINE_VERSION", "EngineError", "annotate", "check", "fix", "score"]
