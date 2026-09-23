"""Lumen-method pre-filter: installed flux vs required flux, before any physics.

Standalone: usable without the search (e.g. UI hints, quote estimators).
Conservative by design — UF is an estimate, so the gate only rejects the
hopeless (< 0.4x target) and the absurd (> 2.5x cap), never edge-feasible.
"""

from __future__ import annotations

from app.providers import StandardTarget
from app.services.vector_math import EPS

# Gate band on predicted_avg / target (low side) and predicted_avg / cap.
_GATE_MIN_RATIO = 0.4
_GATE_MAX_RATIO = 2.5

_UF_FLOOR = 0.2
_UF_CEILING = 0.75


def room_uf(
    polygon: list[tuple[float, float]],
    mount_h: float,
    work_z: float,
    wall_reflectance: float,
) -> float:
    """Utilization factor from room index k = L*W / (Hm*(L+W)).

    Base curve 0.72*k/(k+0.75) fits direct-luminaire UF tables at 0.7/0.5/0.2
    reflectances (k=0.6->0.32, 1.0->0.41, 2.0->0.52, 3.0->0.58, 5.0->0.63),
    corrected x(0.7+0.6*wall_rho) so the 0.5 default is neutral.
    ponytail: bbox dims for non-rectangular rooms; per-class tables when we
    carry indirect/linear fixtures.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    length, width = max(xs) - min(xs), max(ys) - min(ys)
    hm = mount_h - work_z
    if length <= EPS or width <= EPS or hm <= EPS:
        return _UF_FLOOR
    k = length * width / (hm * (length + width))
    uf = 0.72 * k / (k + 0.75) * (0.7 + 0.6 * wall_reflectance)
    return max(_UF_FLOOR, min(_UF_CEILING, uf))


def required_flux(target_avg: float, area: float, uf: float, maintenance: float) -> float:
    """Total room lumens needed for target_avg ("total lumen of area lux")."""
    if uf <= EPS or maintenance <= EPS or area <= EPS:
        return 0.0
    return target_avg * area / (uf * maintenance)


def passes_lumen_gate(installed: float, target: StandardTarget, area: float, uf: float,
                      maintenance: float) -> bool:
    """True when installed lumens plausibly reach target without wild overlight."""
    predicted = installed * uf * maintenance / area if area > EPS else 0.0
    cap = target.avg_lux * (1.0 + target.max_overdesign)
    return target.avg_lux * _GATE_MIN_RATIO <= predicted <= cap * _GATE_MAX_RATIO
