"""L-shape DIALux-parity sweep: isolate mesh gain vs bounce-truncation cost.

Configs (same geometry/seeds, varying only mesh + solver):
  A. fine mesh + fixed 5       (previous default)
  B. coarse mesh + fixed 5     (isolates the mesh gain under identical solver)
  C. fine mesh + fixed 10
  E. fine mesh + converged     (current default: floor tol 0.1 lux, cap 25)

Known reference: pre-change code (coarse mesh + exact inv) gave
avg=369.6 min=290.6 max=428.4 in ~110s. DIALux: avg=372 min=303 max=426.
"""
from __future__ import annotations

import logging
import time

from app.schemas.calculate import CalculateRequest
from app.schemas.geometry import Point2D
from app.schemas.grid import AxisGrid, GridInput
from app.services.calculate_service import calculate

logging.basicConfig(level=logging.WARNING)

POLY = [
    (6.585, 3.2), (9.835, 3.2), (9.835, 5.58),
    (8.625, 5.58), (8.625, 6.53), (6.585, 6.52),
]


def payload() -> CalculateRequest:
    return CalculateRequest(
        polygon=[Point2D(x=x, y=y) for x, y in POLY],
        height=4, ceilingHeight=4, mountingHeight=3,
        workPlaneHeight=0, wallZone=0.25,
        grid=GridInput(
            x=AxisGrid(spacing=1.62, offsetBeginning=0.81, offsetEnding=0),
            y=AxisGrid(spacing=1.66, offsetBeginning=0.83, offsetEnding=0),
        ),
    )


def decompose(result):
    vals = result.totalFloorIlluminance.values
    i_min = vals.index(min(vals))
    i_max = vals.index(max(vals))
    direct = [0.0] * len(vals)
    for m in result.directFloorMatrices.values():
        for i, v in enumerate(m.values):
            direct[i] += v
    indirect = [0.0] * len(vals)
    for m in result.indirectFloorMatrices.values():
        for i, v in enumerate(m.values):
            indirect[i] += v
    return {
        "avg": result.evaluation.average,
        "min": result.evaluation.minimum,
        "max": result.evaluation.maximum,
        "direct_at_max": direct[i_max],
        "indirect_at_max": indirect[i_max],
        "direct_at_min": direct[i_min],
        "indirect_at_min": indirect[i_min],
    }


def run(name: str, **kw):
    ies = open("demo/sample.ies").read()
    t0 = time.perf_counter()
    r = calculate(payload(), ies, **kw)
    dt = time.perf_counter() - t0
    d = decompose(r)
    print(
        f"{name}: dt={dt:.0f}s bounces={r.bounces} "
        f"avg={d['avg']:.1f} min={d['min']:.1f} max={d['max']:.1f} | "
        f"max: direct={d['direct_at_max']:.1f} indirect={d['indirect_at_max']:.1f} | "
        f"min: direct={d['direct_at_min']:.1f} indirect={d['indirect_at_min']:.1f}",
        flush=True,
    )


if __name__ == "__main__":
    run("A fine@5      ", num_bounces=5, use_fine_mesh=True)
    run("B coarse@5    ", num_bounces=5, use_fine_mesh=False)
    run("C fine@10     ", num_bounces=10, use_fine_mesh=True)
    run("E default-conv")
