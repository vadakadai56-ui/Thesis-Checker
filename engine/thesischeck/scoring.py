"""The readiness score (BUILD_PROMPT §4c). A fixed formula, shown to users under
"How is this calculated?":

    penalty = Σ over rules of  weight(severity) × min(number of findings, 5)
    score   = round(100 × e^(−penalty / 60)), between 0 and 100
    weights: error 5, warning 2, info 0.5

Counting at most 5 findings per rule stops one repeated problem (e.g. the same
wrong font in 200 paragraphs) from swamping everything else. If a *blocking* rule
fails (a missing required part or title-page field) the score is capped at 69,
so the thesis can never look "ready" while something essential is missing.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from typing import Any

from .model import Finding

WEIGHTS = {"error": 5.0, "warning": 2.0, "info": 0.5}
MAX_COUNT_PER_RULE = 5
SCALE = 60.0
BLOCKING_CAP = 69
BANDS = ((90, "Ready"), (70, "Nearly ready"), (0, "Needs work"))
SCORE_VERSION = 1


def band_for(value: int) -> str:
    """'Ready' (90–100), 'Nearly ready' (70–89) or 'Needs work' (0–69)."""
    return next(label for threshold, label in BANDS if value >= threshold)


def score(findings: Iterable[Finding], blocking_rules: set[str]) -> dict[str, Any]:
    """Compute the score dict for a report: {value, band, penalty, capped}."""
    remaining = [f for f in findings if not f.fixed]
    per_rule = Counter(f.rule_id for f in remaining)
    severity = {f.rule_id: f.severity for f in remaining}
    penalty = sum(
        WEIGHTS[severity[rule_id]] * min(count, MAX_COUNT_PER_RULE)
        for rule_id, count in per_rule.items()
    )
    value = max(0, min(100, round(100 * math.exp(-penalty / SCALE))))
    capped = bool(blocking_rules & set(per_rule)) and value > BLOCKING_CAP
    if capped:
        value = BLOCKING_CAP
    band = band_for(value)
    return {
        "version": SCORE_VERSION,
        "value": value,
        "band": band,
        "penalty": round(penalty, 2),
        "capped": capped,
    }
