import json
import math
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    StandardTarget,
)
from app.schemas.calculate import (
    CalculateRequest,
    ComplianceTargetInput,
    FixturePlacementDto,
)
from app.schemas.geometry import Point2D
from app.schemas.grid import GridCount, GridInput, GridSpacing
from app.services.calculate_service import calculate, calculate_extended
from tests.ies_sample import SAMPLE_IES, ies_with

POLY = [Point2D(x=0, y=0), Point2D(x=6, y=0), Point2D(x=6, y=4), Point2D(x=0, y=4)]


def test_grid_count_mode():
    payload = CalculateRequest(
        polygon=POLY,
        ceilingHeight=3.0,
        mountingHeight=3.0,
        grid=GridInput(count=GridCount(countX=3, countY=2, offsetFraction=0.5)),
    )
    res = calculate(payload, SAMPLE_IES)
    # nx=3, ny=2 -> 6 fixtures
    assert len(res.fixtures) == 6
    xs = sorted({round(f.position.x, 2) for f in res.fixtures})
    ys = sorted({round(f.position.y, 2) for f in res.fixtures})
    assert len(xs) == 3
    assert len(ys) == 2
    # In a 6x4 room with nx=3, Sx = 6/3 = 2m, offset = 1m -> xs = [1.0, 3.0, 5.0]
    assert xs == [1.0, 3.0, 5.0]
    # In a 6x4 room with ny=2, Sy = 4/2 = 2m, offset = 1m -> ys = [1.0, 3.0]
    assert ys == [1.0, 3.0]


def test_grid_spacing_autocenter_mode():
    payload = CalculateRequest(
        polygon=POLY,
        ceilingHeight=3.0,
        mountingHeight=3.0,
        grid=GridInput(spacing=GridSpacing(spacingX=2.0, spacingY=2.0, autoCenter=True)),
    )
    res = calculate(payload, SAMPLE_IES)
    # 6m span with Sx=2.0 -> nx=3 (centered: 1.0, 3.0, 5.0)
    # 4m span with Sy=2.0 -> ny=2 (centered: 1.0, 3.0)
    assert len(res.fixtures) == 6
    xs = sorted({round(f.position.x, 2) for f in res.fixtures})
    assert xs == [1.0, 3.0, 5.0]


def test_free_placement_with_tilt_angle():
    payload = CalculateRequest(
        polygon=POLY,
        ceilingHeight=3.0,
        mountingHeight=3.0,
        luminaireRotation=0.0,
        fixtures=[
            FixturePlacementDto(id="F1", x=3.0, y=2.0, z=2.8, tiltAngle=45.0, rotation=0.0)
        ],
    )
    res = calculate(payload, SAMPLE_IES)
    assert len(res.fixtures) == 1
    f = res.fixtures[0]
    assert f.position.z == pytest.approx(2.8)
    # 45 deg tilt along rotation 0 -> aimDirection = (sin(45), 0, -cos(45))
    expected_x = math.sin(math.radians(45.0))
    expected_z = -math.cos(math.radians(45.0))
    assert f.aimDirection.x == pytest.approx(expected_x, rel=1e-3)
    assert f.aimDirection.y == pytest.approx(0.0, abs=1e-5)
    assert f.aimDirection.z == pytest.approx(expected_z, rel=1e-3)


def test_custom_physics_and_compliance():
    payload = CalculateRequest(
        polygon=POLY,
        ceilingHeight=3.0,
        mountingHeight=3.0,
        wallReflectance=0.7,
        floorReflectance=0.3,
        ceilingReflectance=0.8,
        maintenanceFactor=0.9,
        bounces=2,
        grid=GridInput(count=GridCount(countX=2, countY=2)),
        compliance=ComplianceTargetInput(targetLux=100.0, targetUniformity=0.3),
    )
    res = calculate(payload, SAMPLE_IES)
    assert res.wallReflectance == 0.7
    assert res.floorReflectance == 0.3
    assert res.ceilingReflectance == 0.8
    assert res.maintenanceFactor == 0.9
    assert res.bounces == 2
    assert res.compliance is not None
    assert res.compliance.targetLux == 100.0
    assert res.compliance.targetUniformity == 0.3
    assert isinstance(res.compliance.compliant, bool)
    assert res.compliance.luxGap == pytest.approx(res.evaluation.average - 100.0, abs=0.05)


def test_compact_matrix_mode():
    # includeWallCeilingMatrices = False
    payload = CalculateRequest(
        polygon=POLY,
        ceilingHeight=3.0,
        mountingHeight=3.0,
        grid=GridInput(count=GridCount(countX=2, countY=2)),
        includeWallCeilingMatrices=False,
    )
    res = calculate(payload, SAMPLE_IES)
    assert res.totalFloorIlluminance.values
    # Check variant results has compact matrices
    assert len(res.results) == 1
    v = res.results[0]
    assert v.totalFloorIlluminance.values
    assert not v.directWallMatrices
    assert not v.indirectWallMatrices


def test_multi_variant_json_endpoint():
    # Setup test app with InMemoryFixtureProvider and InMemoryStandardProvider
    spec1 = FixtureSpec(
        id="var-1",
        fixture_id="fix-1",
        variant_id="var-1",
        ies_text=ies_with(lumens=1000.0),
        wattage=15.0,
        lumens=1000.0,
        is_main_solution=True,
        applications=("interior",),
    )
    spec2 = FixtureSpec(
        id="var-2",
        fixture_id="fix-2",
        variant_id="var-2",
        ies_text=ies_with(lumens=2000.0),
        wattage=30.0,
        lumens=2000.0,
        is_main_solution=True,
        applications=("interior",),
    )
    fix_prov = InMemoryFixtureProvider({spec1.id: spec1, spec2.id: spec2})
    std_prov = InMemoryStandardProvider(
        {"office": StandardTarget(activity_id="office", avg_lux=200.0, uniformity=0.4)}
    )

    from app.controllers.calculate_controller import _fixture_provider, _standard_provider
    app.dependency_overrides[_fixture_provider] = lambda: fix_prov
    app.dependency_overrides[_standard_provider] = lambda: std_prov

    client = TestClient(app)
    try:
        # 1. Grid with default variantId
        body = {
            "polygon": [{"x": p.x, "y": p.y} for p in POLY],
            "ceilingHeight": 3.0,
            "mountingHeight": 3.0,
            "grid": {"count": {"countX": 2, "countY": 2}},
            "variantId": "var-1",
            "compliance": {"activityId": "office"},
        }
        resp = client.post("/calculate", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["fixtures"]) == 4
        assert all(f["variantId"] == "var-1" for f in data["fixtures"])
        assert data["powerW"] == 15.0 * 4  # 60.0 W
        assert data["powerDensity"] == pytest.approx(60.0 / (6.0 * 4.0), rel=1e-3)
        assert data["compliance"] is not None

        # 2. Heterogeneous free fixtures (F1 has var-1, F2 has var-2)
        body_hetero = {
            "polygon": [{"x": p.x, "y": p.y} for p in POLY],
            "ceilingHeight": 3.0,
            "mountingHeight": 3.0,
            "fixtures": [
                {"id": "F1", "x": 1.5, "y": 2.0, "variantId": "var-1"},
                {"id": "F2", "x": 4.5, "y": 2.0, "variantId": "var-2"},
            ],
            "compliance": {"activityId": "office"},
        }
        resp_hetero = client.post("/calculate", json=body_hetero)
        assert resp_hetero.status_code == 200, resp_hetero.text
        data_hetero = resp_hetero.json()
        assert len(data_hetero["fixtures"]) == 2
        f1 = next(f for f in data_hetero["fixtures"] if f["id"] == "F1")
        f2 = next(f for f in data_hetero["fixtures"] if f["id"] == "F2")
        assert f1["variantId"] == "var-1"
        assert f2["variantId"] == "var-2"
        # Total power = 15.0 + 30.0 = 45.0 W
        assert data_hetero["powerW"] == 45.0
        assert data_hetero["powerDensity"] == pytest.approx(45.0 / (6.0 * 4.0), rel=1e-3)
    finally:
        app.dependency_overrides.clear()


def test_calculate_allows_non_main_solution_variants():
    # Non-main solution and mismatched application (e.g. industrial fixture in 3.0m interior room)
    non_main_spec = FixtureSpec(
        id="var-non-main",
        fixture_id="fix-custom",
        variant_id="var-non-main",
        ies_text=ies_with(lumens=1500.0),
        wattage=25.0,
        lumens=1500.0,
        is_main_solution=False,
        applications=("industrial",),
    )
    fix_prov = InMemoryFixtureProvider({non_main_spec.id: non_main_spec})

    from app.controllers.calculate_controller import _fixture_provider
    app.dependency_overrides[_fixture_provider] = lambda: fix_prov

    client = TestClient(app)
    try:
        body = {
            "polygon": [{"x": p.x, "y": p.y} for p in POLY],
            "ceilingHeight": 3.0,
            "mountingHeight": 3.0,
            "grid": {"count": {"countX": 2, "countY": 1}},
            "variantId": "var-non-main",
        }
        resp = client.post("/calculate", json=body)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["fixtures"]) == 2
        assert all(f["variantId"] == "var-non-main" for f in data["fixtures"])
        assert data["powerW"] == 25.0 * 2  # 50.0 W
    finally:
        app.dependency_overrides.clear()

