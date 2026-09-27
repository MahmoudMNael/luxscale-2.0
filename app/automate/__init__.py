"""Best-grid automater. Grid strategy in layouts, physics in engine."""

from app.automate.layouts import LayoutSpec, auto_spacing_range, enumerate_layouts, frange, placements_for_layout
from app.automate.lumen import passes_lumen_gate, required_flux, room_uf
from app.automate.search import (
    Outcome,
    Solution,
    automate,
    best_per_variant,
    classify_miss,
    is_compliant,
    pick_diverse,
    pick_overcap,
    shortlist_for_key,
)

__all__ = [
    "LayoutSpec",
    "Outcome",
    "Solution",
    "automate",
    "auto_spacing_range",
    "best_per_variant",
    "classify_miss",
    "enumerate_layouts",
    "frange",
    "is_compliant",
    "passes_lumen_gate",
    "pick_diverse",
    "pick_overcap",
    "placements_for_layout",
    "required_flux",
    "room_uf",
    "shortlist_for_key",
]
