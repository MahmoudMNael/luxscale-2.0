"""Engine placements + providers check: parity, heterogeneity, standalone steps."""

import json

import pytest

from app.domain.exceptions import ProviderError
from app.domain.models import FixturePlacement
from app.engine import (
    EngineInput,
    PhysicsOptions,
    RoomInput,
    build_eval_grids,
    build_room,
    build_solver_cache,
    calculate,
    resolve_fixtures,
    run,
)
from app.main import app
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    RestFixtureProvider,
    RestStandardProvider,
    StandardTarget,
)
from app.schemas.calculate import CalculateRequest
from app.schemas.geometry import Point2D
from app.schemas.grid import AxisGrid, GridInput
from app.services import calculate_service
from app.services.ies_service import load_ies
from fastapi.testclient import TestClient
from tests.ies_sample import SAMPLE_IES, ies_with

POLY = [(0, 0), (4, 0), (4, 4), (0, 4)]
FOUR = [
    FixturePlacement(id="F1", x=1, y=1),
    FixturePlacement(id="F2", x=3, y=1),
    FixturePlacement(id="F3", x=1, y=3),
    FixturePlacement(id="F4", x=3, y=3),
]


def _room_input() -> RoomInput:
    return RoomInput(polygon=POLY, ceiling_height=3.0, floor_zone=0.25, wall_zone=0.25)


def test_grid_placements_parity():
    grid_result = calculate_service.calculate(
        CalculateRequest(
            polygon=[Point2D(x=x, y=y) for x, y in POLY],
            height=3,
            floorZone=0.25,
            wallZone=0.25,
            grid=GridInput(
                x=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
                y=AxisGrid(spacing=2, offsetBeginning=1, offsetEnding=1),
            ),
        ),
        SAMPLE_IES,
    )
    profile = load_ies(SAMPLE_IES)
    free = calculate(EngineInput(room=_room_input(), placements=FOUR), {"default": profile})
    assert [f.id for f in free.fixtures] == ["F1", "F2", "F3", "F4"]
    assert [(f.position[0], f.position[1]) for f in free.fixtures] == [
        (f.position.x, f.position.y) for f in grid_result.fixtures
    ]
    assert free.evaluation.average == pytest.approx(grid_result.evaluation.average)
    assert free.evaluation.uniformity == pytest.approx(grid_result.evaluation.uniformity)


def test_heterogeneous_profiles_and_rotation():
    profiles = {"a": load_ies(ies_with(lumens=1000.0)), "b": load_ies(ies_with(lumens=2000.0))}
    one = calculate(
        EngineInput(
            room=_room_input(),
            placements=[FixturePlacement(id="F1", x=2, y=2, rotation=90.0, ies_ref="a")],
        ),
        profiles,
    )
    two = calculate(
        EngineInput(
            room=_room_input(),
            placements=[FixturePlacement(id="F1", x=2, y=2, rotation=90.0, ies_ref="b")],
        ),
        profiles,
    )
    assert two.evaluation.average == pytest.approx(2 * one.evaluation.average, rel=1e-9)
    assert one.fixtures[0].rotation == 90.0


def test_standalone_steps_without_facade():
    room, _, mount_h, work_z = build_room(_room_input())
    assert len(room.walls) == 4
    evaluation = build_eval_grids(room, work_z, 0.25, 0.25)
    assert evaluation.floor
    cache = build_solver_cache(room, evaluation, room.height, PhysicsOptions(bounces=0))
    assert cache.sources
    fixtures = resolve_fixtures(room, FOUR[:2], {"default": load_ies(SAMPLE_IES)}, mount_h)
    assert [f.id for f in fixtures] == ["F1", "F2"]
    result = run(fixtures, room, evaluation, cache, PhysicsOptions(bounces=0))
    assert result.evaluation.average > 0
    assert result.bounces == 0


def test_outside_polygon_skipped_and_empty_raises():
    from app.domain.exceptions import NoFixturesError

    room, _, mount_h, _ = build_room(_room_input())
    kept = resolve_fixtures(
        room,
        [FixturePlacement(id="in", x=2, y=2), FixturePlacement(id="out", x=99, y=99)],
        {"default": load_ies(SAMPLE_IES)},
        mount_h,
    )
    assert [f.id for f in kept] == ["in"]
    with pytest.raises(NoFixturesError):
        resolve_fixtures(
            room, [FixturePlacement(id="out", x=99, y=99)], {"default": load_ies(SAMPLE_IES)}, mount_h
        )


def test_providers_mocks_and_rest_errors():
    standards = InMemoryStandardProvider(
        {"office": StandardTarget(activity_id="office", avg_lux=500, uniformity=0.6)}
    )
    assert standards.get_target("office").avg_lux == 500
    with pytest.raises(ProviderError):
        standards.get_target("nope")

    fixtures = InMemoryFixtureProvider(
        {
            "f1": FixtureSpec(
                id="f1", fixture_id="fix-1", variant_id="f1",
                ies_text=SAMPLE_IES, wattage=32, lumens=3200.0,
                applications=("interior",),
            )
        }
    )
    assert fixtures.get_many(["f1"])[0].wattage == 32
    assert fixtures.list_main_variants("interior")[0].lumens == 3200.0
    assert fixtures.get_variants(["f1"], "interior")[0].id == "f1"
    with pytest.raises(ProviderError):
        fixtures.get_variants(["f1"], "industrial")

    with pytest.raises(ProviderError):  # base URL not configured
        RestStandardProvider(base_url="").get_target("office")
    with pytest.raises(ProviderError):  # unreachable host maps to 502, not raw URLError
        RestStandardProvider(base_url="http://127.0.0.1:1", timeout_s=0.2).get_target("office")
    with pytest.raises(ProviderError):
        RestFixtureProvider(base_url="http://127.0.0.1:1", timeout_s=0.2).list_main_variants(
            "interior"
        )


def test_placements_endpoint_with_default_ies():
    client = TestClient(app)
    payload = {
        "polygon": [{"x": x, "y": y} for x, y in POLY],
        "height": 3,
        "fixtures": [{"x": 1, "y": 1}, {"x": 3, "y": 3, "rotation": 90}],
    }
    response = client.post(
        "/calculate",
        data={"payload": json.dumps(payload)},
        files={"iesFile": ("lamp.ies", SAMPLE_IES, "text/plain")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [f["id"] for f in body["fixtures"]] == ["F1", "F2"]
    assert body["fixtures"][1]["rotation"] == 90
    assert body["evaluation"]["average"] > 0


def test_placements_endpoint_multi_ies_by_filename():
    client = TestClient(app)
    payload = {
        "polygon": [{"x": x, "y": y} for x, y in POLY],
        "height": 3,
        "fixtures": [{"x": 1, "y": 1, "iesRef": "dim.ies"}, {"x": 3, "y": 3, "iesRef": "bright.ies"}],
    }
    response = client.post(
        "/calculate",
        data={"payload": json.dumps(payload)},
        files=[
            ("iesFiles", ("dim.ies", ies_with(lumens=1000.0), "text/plain")),
            ("iesFiles", ("bright.ies", ies_with(lumens=2000.0), "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["evaluation"]["average"] > 0
