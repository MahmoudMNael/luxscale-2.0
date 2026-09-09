from __future__ import annotations

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix


def sum_matrices(matrices: list[Matrix]) -> Matrix:
    if not matrices:
        raise GeometryError("Cannot sum an empty matrix list.")
    n = len(matrices[0].values)
    if any(len(matrix.values) != n for matrix in matrices):
        raise GeometryError("Cannot sum matrices with different patch layouts.")
    values = [sum(matrix.values[i] for matrix in matrices) for i in range(n)]
    return Matrix(values, {"kind": "sum", "sources": [matrix.metadata for matrix in matrices]})


def apply_maintenance_factor(matrix: Matrix, factor: float) -> Matrix:
    return Matrix(
        [value * factor for value in matrix.values],
        {**matrix.metadata, "maintained": True, "maintenanceFactor": factor},
    )
