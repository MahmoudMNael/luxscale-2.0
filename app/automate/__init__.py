"""Best-grid optimizer. Grid strategy in layouts, physics in engine."""

from app.optimize.layouts import LayoutSpec, enumerate_layouts, frange, placements_for_layout
from app.optimize.lumen import passes_lumen_gate, required_flux, room_uf
from app.optimize.search import Outcome, Solution, is_compliant, optimize, pick_diverse

__all__ = [
    "LayoutSpec",
    "Outcome",
    "Solution",
    "enumerate_layouts",
    "frange",
    "is_compliant",
    "optimize",
    "passes_lumen_gate",
    "pick_diverse",
    "placements_for_layout",
    "required_flux",
    "room_uf",
]
