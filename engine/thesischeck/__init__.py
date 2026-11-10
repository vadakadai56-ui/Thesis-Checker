"""ThesisCheck rules engine — plain Python, no browser code (BUILD_PROMPT §3, §7).

Public API: check(), fix(), annotate(), score(). In stage 1 only check() works.
"""

from .api import ENGINE_VERSION, annotate, check, fix, score
from .model import EngineError

__all__ = ["ENGINE_VERSION", "EngineError", "annotate", "check", "fix", "score"]
