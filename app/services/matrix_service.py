from __future__ import annotations

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix


def sum_matrices(matrices: list[Matrix]) -> Matrix:
    if not matrices:
        raise GeometryError("Cannot sum an empty matrix list.")
    # C++ fast path. Falls back on any issue.
    try:
        from app.services._luxcore_bridge import LuxCoreRuntime

        if LuxCoreRuntime().module is not None:
            import numpy as _np

            _mod = LuxCoreRuntime().module
            stacked = _mod.sum_matrices(
                [ _np.ascontiguousarray(_np.asarray(m.values, dtype=_np.float64)) for m in matrices ]
            )
            n = len(matrices[0].values)
            if any(len(matrix.values) != n for matrix in matrices):
                raise GeometryError("Cannot sum matrices with different patch layouts.")
            return Matrix([float(v) for v in stacked.tolist()],
                          {"kind": "sum", "sources": [matrix.metadata for matrix in matrices]})
    except GeometryError:
        raise
    except Exception:
        pass
    n = len(matrices[0].values)
    if any(len(matrix.values) != n for matrix in matrices):
        raise GeometryError("Cannot sum matrices with different patch layouts.")
    values = [sum(matrix.values[i] for matrix in matrices) for i in range(n)]
    return Matrix(values, {"kind": "sum", "sources": [matrix.metadata for matrix in matrices]})


def apply_maintenance_factor(matrix: Matrix, factor: float) -> Matrix:
    # C++ fast path (OpenMP scale). Falls back on any issue.
    try:
        from app.services._luxcore_bridge import LuxCoreRuntime

        if LuxCoreRuntime().module is not None:
            import numpy as _np

            _mod = LuxCoreRuntime().module
            scaled = _mod.scale_vector(
                _np.ascontiguousarray(_np.asarray(matrix.values, dtype=_np.float64)), float(factor)
            )
            return Matrix(
                [float(v) for v in scaled.tolist()],
                {**matrix.metadata, "maintained": True, "maintenanceFactor": factor},
            )
    except Exception:
        pass
    return Matrix(
        [value * factor for value in matrix.values],
        {**matrix.metadata, "maintained": True, "maintenanceFactor": factor},
    )
