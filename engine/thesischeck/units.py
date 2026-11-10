"""Unit conversions.

Word stores page sizes and margins in *twips* (twentieths of a point; 1440 per inch)
and font sizes in *half-points*. People think in centimetres and points. We keep
the internal maths in Word's own units (so there is no rounding drift) and only
convert to cm / pt when we show a value to the user.
"""

from __future__ import annotations

TWIPS_PER_INCH = 1440
CM_PER_INCH = 2.54
TWIPS_PER_CM = TWIPS_PER_INCH / CM_PER_INCH  # ≈ 566.93

# Standard paper sizes as (width, height) in twips, portrait orientation.
# These are the exact numbers Word writes into <w:pgSz>.
PAPER_SIZES_TWIPS: dict[str, tuple[int, int]] = {
    "A4": (11906, 16838),  # 21.0 × 29.7 cm
    "Letter": (12240, 15840),  # 8.5 × 11 in
}

# Two paper sizes count as "the same" if they differ by at most this much.
# 20 twips ≈ 0.035 cm, far smaller than any real paper-size difference.
PAPER_TOLERANCE_TWIPS = 20


def cm_to_twips(cm: float) -> float:
    return cm * TWIPS_PER_CM


def twips_to_cm(twips: float) -> float:
    return twips / TWIPS_PER_CM


def half_points_to_pt(half_points: int) -> float:
    return half_points / 2


def fmt_cm(twips: float) -> str:
    """Format a twips value as e.g. '2.50 cm' for messages."""
    return f"{twips_to_cm(twips):.2f} cm"


def fmt_pt(pt: float) -> str:
    """Format a point size without a pointless '.0' (12 pt, 10.5 pt)."""
    return f"{pt:g} pt"


def paper_name(width: int, height: int) -> str | None:
    """Return 'A4' / 'Letter' if the size matches one (either orientation), else None."""
    short, long_ = sorted((width, height))
    for name, (w, h) in PAPER_SIZES_TWIPS.items():
        if abs(short - w) <= PAPER_TOLERANCE_TWIPS and abs(long_ - h) <= PAPER_TOLERANCE_TWIPS:
            return name
    return None
