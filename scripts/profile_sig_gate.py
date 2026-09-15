"""Sig-gate impact test: measure how much of the 8.2-lux L-shape gap
comes from the ``sig`` gate zeroing occluded pairs below 1% of gmax.

Runs the L-shape DIALux reference twice:
  A. default  (sig gate on, g > 0.01*gmax)
  B. no-sig   (sig gate off, _segment_fraction for ALL occluded pairs)

DIALux reference: avg=372 min=303 max=426.
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
        "uniformity": result.evaluation.uniformity,
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
    meta = {}
    print(
        f"{name}: dt={dt:.0f}s bounces={r.bounces} "
        f"avg={d['avg']:.1f} min={d['min']:.1f} max={d['max']:.1f} "
        f"U0={d['uniformity']:.3f} | "
        f"max: direct={d['direct_at_max']:.1f} indirect={d['indirect_at_max']:.1f} | "
        f"min: direct={d['direct_at_min']:.1f} indirect={d['indirect_at_min']:.1f}",
        flush=True,
    )
    return d


if __name__ == "__main__":
    print("DIALux reference: avg=372 min=303 max=426 U0=0.815")
    print()
    a = run("A sig-gate ON ", disable_sig_gate=False)
    b = run("B sig-gate OFF", disable_sig_gate=True)
    print()
    print("Delta (B - A):")
    for k in ("avg", "min", "max"):
        print(f"  {k}: {b[k] - a[k]:+.1f} lux")
    print(f"  U0: {b['uniformity'] - a['uniformity']:+.3f}")
