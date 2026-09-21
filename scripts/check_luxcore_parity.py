#!/usr/bin/env python3
"""Parity + performance check: C++ luxcore backend vs pure-Python fallback.

Usage:
    python scripts/check_luxcore_parity.py        # runs both backends as
                                                  # subprocesses, compares
    LUXCORE_ENABLED=0|1 python scripts/check_luxcore_parity.py --dump _file.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

CASES = ["rect-8x6", "l-room"]

# Ensure `import luxcore` (in-place built extension at the repo root) works
# regardless of the invocation directory / sys.path[0].
import pathlib as _pl

_ROOT = str(_pl.Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _payload(case: str):
    from app.schemas.calculate import CalculateRequest
    from app.schemas.geometry import Point2D
    from app.schemas.grid import AxisGrid, GridInput

    def grid(s=2.0, o=1.0) -> GridInput:
        return GridInput(x=AxisGrid(spacing=s, offsetBeginning=o, offsetEnding=o),
                         y=AxisGrid(spacing=s, offsetBeginning=o, offsetEnding=o))

    if case == "rect-8x6":
        poly = [(0, 0), (8, 0), (8, 6), (0, 6)]
    else:
        poly = [(0, 0), (8, 0), (8, 3), (3, 3), (3, 8), (0, 8)]
    return CalculateRequest(
        polygon=[Point2D(x=x, y=y) for x, y in poly], height=3.0, grid=grid())


def _dump(path: str) -> None:
    from app.services import calculate_service
    from app.services._luxcore_bridge import LuxCoreRuntime

    ies = open("demo/sample.ies").read()
    print(f"backend={LuxCoreRuntime().backend_name()} "
          f"available={LuxCoreRuntime().is_available()}", flush=True)
    out = {}
    for case in CASES:
        t0 = time.perf_counter()
        res = calculate_service.calculate(_payload(case), ies)
        dt = time.perf_counter() - t0
        out[case] = {
            "dt": dt,
            "fixtures": [f.id for f in res.fixtures],
            "floor": res.totalFloorIlluminance.values,
            "ceiling": res.totalCeilingIlluminance.values,
            "walls": {k: v.values for k, v in res.totalWallIlluminance.items()},
            "direct_floor": {k: v.values for k, v in res.directFloorMatrices.items()},
            "indirect_floor": {k: v.values for k, v in res.indirectFloorMatrices.items()},
            "avg": res.evaluation.average,
        }
        print(f"{case}: {dt:.2f}s avg={res.evaluation.average:.4f}", flush=True)
    with open(path, "w") as fh:
        json.dump(out, fh)


def _compare(a_path: str, b_path: str) -> None:
    a = json.load(open(a_path))
    b = json.load(open(b_path))

    def close(x: list[float], y: list[float], tol: float, what: str) -> float:
        assert len(x) == len(y), (what, len(x), len(y))
        worst = max(abs(u - v) / max(1.0, abs(u), abs(v)) for u, v in zip(x, y))
        assert worst <= tol, f"{what}: max rel diff {worst}"
        return worst

    for case in CASES:
        r, c = a[case], b[case]
        assert r["fixtures"] == c["fixtures"]
        w1 = close(r["floor"], c["floor"], 1e-6, f"{case}/floor")
        w2 = close(r["ceiling"], c["ceiling"], 1e-6, f"{case}/ceiling")
        for k in r["walls"]:
            close(r["walls"][k], c["walls"][k], 1e-6, f"{case}/wall-{k}")
        for k in r["direct_floor"]:
            close(r["direct_floor"][k], c["direct_floor"][k], 1e-6, f"{case}/direct-{k}")
        for k in r["indirect_floor"]:
            close(r["indirect_floor"][k], c["indirect_floor"][k], 2e-6,
                  f"{case}/indirect-{k}")
        assert abs(r["avg"] - c["avg"]) / max(1.0, r["avg"]) < 1e-6
        speed = r["dt"] / c["dt"]
        print(f"{case}: floor diff={w1:.2e} ceiling diff={w2:.2e} "
              f"avg {r['avg']:.4f}->{c['avg']:.4f} "
              f"python={r['dt']:.2f}s cpp={c['dt']:.2f}s speedup={speed:.1f}x")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--dump":
        _dump(sys.argv[2])
    else:
        import os

        env = dict(os.environ)
        for tag, flag in (("py", "0"), ("cpp", "1")):
            e = dict(env, LUXCORE_ENABLED=flag)
            subprocess.run([sys.executable, __file__, "--dump", f"/tmp/parity_{tag}.json"],
                           check=True, env=e)
        _compare("/tmp/parity_py.json", "/tmp/parity_cpp.json")
        print("PARITY OK")
