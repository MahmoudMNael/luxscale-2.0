import math

import pytest

from app.app_settings import FLOOR_BORDER, MAINTENANCE_FACTOR, WORK_PLANE_HEIGHT
from app.schemas.calculate import CalculateRequest
from app.schemas.grid import AxisGrid, GridInput
from app.schemas.geometry import Point2D
from app.services.calculate_service import calculate
from app.services.vector_math import EPS, en12464_spacing
from tests.ies_sample import SAMPLE_IES


def _payload() -> CalculateRequest:
    return CalculateRequest(
        polygon=[Point2D(x=0, y=0), Point2D(x=4, y=0), Point2D(x=4, y=4), Point2D(x=0, y=4)],
        height=3,
        grid=GridInput(
            x=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
            y=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
        ),
    )


def test_pipeline_floor_lux_and_maintenance_metadata():
    result = calculate(_payload(), SAMPLE_IES)
    assert result.fixtures
    fixture = result.fixtures[0]
    assert len(fixture.corners) == 4
    assert len(fixture.elements) == 1
    assert fixture.length == 0
    assert fixture.width == 0
    assert fixture.height == 0
    assert result.floorPatches
    assert all(p.center.z == WORK_PLANE_HEIGHT for p in result.floorPatches)
    xs = [p.center.x for p in result.floorPatches]
    ys = [p.center.y for p in result.floorPatches]
    span = 4.0 - 2 * FLOOR_BORDER
    spacing = en12464_spacing(span)
    n = max(1, math.ceil(span / spacing - EPS))
    half = span / n / 2
    assert min(xs) == pytest.approx(FLOOR_BORDER + half)
    assert max(xs) == pytest.approx(4 - FLOOR_BORDER - half)
    assert min(ys) == pytest.approx(FLOOR_BORDER + half)
    assert max(ys) == pytest.approx(4 - FLOOR_BORDER - half)
    assert result.directFloorMatrices[fixture.id].metadata["patchSize"] == pytest.approx(result.floorPatches[0].size)
    total = result.totalFloorIlluminance.values
    assert total
    assert max(total) > 0
    assert result.totalFloorIlluminance.metadata["maintained"] is True
    assert result.totalFloorIlluminance.metadata["maintenanceFactor"] == MAINTENANCE_FACTOR
    assert set(result.directFloorMatrices) == set(result.directWallMatrices[next(iter(result.wallPatches))])
    combined = [0.0] * len(total)
    for matrix in result.directFloorMatrices.values():
        assert matrix.metadata["maintained"] is True
        for i, value in enumerate(matrix.values):
            combined[i] += value
    for matrix in result.indirectFloorMatrices.values():
        for i, value in enumerate(matrix.values):
            combined[i] += value
    assert combined == pytest.approx(total)
