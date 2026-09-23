"""Best-grid automater. Grid strategy in layouts, physics in engine."""

from app.automate.layouts import LayoutSpec, enumerate_layouts, frange, placements_for_layout
from app.automate.lumen import passes_lumen_gate, required_flux, room_uf
from app.automate.search import Outcome, Solution, automate, is_compliant, pick_diverse

__all__ = [
    "LayoutSpec",
    "Outcome",
    "Solution",
    "automate",
    "enumerate_layouts",
    "frange",
    "is_compliant",
    "passes_lumen_gate",
    "pick_diverse",
    "placements_for_layout",
    "required_flux",
    "room_uf",
]
