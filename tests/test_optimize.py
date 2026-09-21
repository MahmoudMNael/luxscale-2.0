"""Optimizer check: compliance, catalog comparison, providers, validation."""

import json

import pytest

from app.main import app
from app.optimize import frange, is_compliant, pick_diverse
from app.optimize.lumen import passes_lumen_gate, required_flux, room_uf
from app.optimize.search import Solution
from app.optimize.layouts import LayoutSpec
from app.controllers.optimize_controller import _fixture_provider, _standard_provider
from app.engine import RoomInput
from app.optimize import optimize as run_search
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    StandardTarget,
)
from app.services.ies_service import installed_flux, load_ies
from fastapi.testclient import TestClient
from tests.ies_sample import SAMPLE_IES, ies_with

ROOM = RoomInput(polygon=[(0, 0), (4, 0), (4, 4), (0, 4)], ceiling_height=3.0,
                 floor_zone=0.25, wall_zone=0.25)
TARGET = StandardTarget(activity_id="t", avg_lux=50.0, uniformity=0.5, max_overdesign=0.3)
DIM = load_ies(SAMPLE_IES)
BRIGHT = load_ies(ies_with(lumens=3000.0))
SPACE = dict(sx_vals=[2.0, 2.5, 3.0], sy_vals=[2.0, 2.5, 3.0], offset_fractions=[0.5],
             rotations=[0.0, 90.0])


def test_single_fixture_finds_compliant_ranked_solutions():
    outcome = run_search(ROOM, {"dim": DIM}, TARGET, **SPACE, top_k=5, stage_b_n=6)
    assert outcome.evaluated_a > 0 and outcome.evaluated_b > 0
    assert len(outcome.solutions) >= 2
    for sol in outcome.solutions:
        assert sol.average >= 50.0 and sol.uniformity >= 0.5
        assert sol.average <= 50.0 * 1.3  # overdesign cap respected
    counts = [s.count for s in outcome.solutions]
    assert counts[0] == min(counts)  # compact first


def test_catalog_brighter_fixture_needs_fewer_fixtures():
    space = dict(SPACE, sx_vals=[2.0, 3.0, 4.0], sy_vals=[2.0, 3.0, 4.0])  # 4m centers 1 fixture
    outcome = run_search(ROOM, {"dim": DIM, "bright": BRIGHT}, TARGET, **space,
                         top_k=6, stage_b_n=8)
    by_key: dict[str, list[int]] = {}
    for sol in outcome.solutions:
        assert is_compliant(sol.average, sol.uniformity, TARGET)
        by_key.setdefault(sol.fixture_key, []).append(sol.count)
    assert set(by_key) <= {"dim", "bright"}
    assert min(by_key["bright"]) < min(by_key["dim"])
    assert min(by_key["bright"]) == 1


def test_lumen_helpers_recover_rated_flux_and_bounded_uf():
    assert installed_flux(DIM) == pytest.approx(1000.0)
    assert installed_flux(BRIGHT) == pytest.approx(3000.0)
    uf_small = room_uf([(0, 0), (4, 0), (4, 4), (0, 4)], 3.0, 0.0, 0.5)
    uf_big = room_uf([(0, 0), (10, 0), (10, 10), (0, 10)], 3.0, 0.0, 0.5)
    assert 0.2 <= uf_small < uf_big <= 0.75
    assert required_flux(50.0, 16.0, uf_small, 0.8) == pytest.approx(800 / (uf_small * 0.8))
    assert passes_lumen_gate(4000.0, TARGET, 16.0, uf_small, 0.8)  # feasible 4x dim
    assert not passes_lumen_gate(500.0, TARGET, 16.0, uf_small, 0.8)  # hopeless
    assert not passes_lumen_gate(50000.0, TARGET, 16.0, uf_small, 0.8)  # absurd


def test_lumen_gate_prunes_hopeless_before_stage_a():
    hopeless = StandardTarget(activity_id="h", avg_lux=500.0, uniformity=0.5,
                              max_overdesign=0.3)
    outcome = run_search(ROOM, {"dim": DIM}, hopeless, **SPACE, top_k=5, stage_b_n=6)
    assert outcome.evaluated_a == 0
    assert outcome.solutions == [] and outcome.closest_miss is None
    assert outcome.pruned["lumen"] == 3 * 3 * 1 * 2  # every enumerated layout


def test_frange_includes_hi_and_compliance_boundaries():
    assert frange(1.5, 2.0, 0.5) == [1.5, 2.0]
    assert is_compliant(50.0, 0.5, TARGET)
    assert is_compliant(65.0, 0.9, TARGET)
    assert not is_compliant(65.1, 0.9, TARGET)
    assert not is_compliant(49.9, 0.9, TARGET)


def test_pick_diverse_caps_and_leads_compact():
    def _sol(count, avg, u0, sx):
        return Solution("f", LayoutSpec(sx=sx, sy=2, ox=1, oy=1, rotation=0),
                        [], count, avg, 40, 80, u0, avg / 50 - 1)
    sols = [_sol(4, 60, 0.66, 2.0), _sol(2, 55, 0.54, 3.0), _sol(6, 52, 0.76, 1.5)]
    picks = pick_diverse(sols, top_k=2)
    assert len(picks) == 2 and picks[0].count == 2


def _payload(**over):
    base = {
        "polygon": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 4}, {"x": 0, "y": 4}],
        "height": 3,
        "floorZone": 0.25,
        "wallZone": 0.25,
        "target": {"avgLux": 50, "uniformity": 0.5, "maxOverdesign": 0.3},
        "search": {
            "spacingX": {"min": 2.0, "max": 3.0, "step": 0.5},
            "spacingY": {"min": 2.0, "max": 3.0, "step": 0.5},
            "offsetFractions": [0.5],
            "rotations": [0.0],
        },
        "topK": 4,
        "stageB": 6,
    }
    return base | over


def test_optimize_endpoint_with_uploads():
    client = TestClient(app)
    response = client.post(
        "/optimize",
        data={"payload": json.dumps(_payload())},
        files=[
            ("iesFiles", ("dim.ies", SAMPLE_IES, "text/plain")),
            ("iesFiles", ("bright.ies", ies_with(lumens=3000.0), "text/plain")),
        ],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["evaluatedA"] > 0 and body["evaluatedB"] > 0
    assert len(body["solutions"]) >= 1
    for sol in body["solutions"]:
        assert sol["average"] >= 50.0 and sol["uniformity"] >= 0.5
        assert sol["average"] <= 65.0
        assert sol["grid"]["spacingX"] > 0 and sol["placements"]


def test_optimize_endpoint_with_providers():
    app.dependency_overrides[_standard_provider] = lambda: InMemoryStandardProvider(
        {"office": StandardTarget(activity_id="office", avg_lux=50, uniformity=0.5,
                                   max_overdesign=0.3)}
    )
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {"cat-dim": FixtureSpec(id="cat-dim", ies_text=SAMPLE_IES, wattage=20.0)}
    )
    try:
        client = TestClient(app)
        payload = _payload(target=None, activityId="office", fixtureIds=["cat-dim"])
        del payload["target"]
        response = client.post("/optimize", data={"payload": json.dumps(payload)})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["solutions"]
        assert all(s["fixtureId"] == "cat-dim" for s in body["solutions"])
        assert all(s["powerW"] == s["fixtureCount"] * 20.0 for s in body["solutions"])
    finally:
        app.dependency_overrides.clear()


def test_optimize_validation():
    client = TestClient(app)
    bad = _payload(target={"avgLux": 50, "uniformity": 0.5}, activityId="office")
    response = client.post(
        "/optimize", data={"payload": json.dumps(bad)},
        files=[("iesFiles", ("dim.ies", SAMPLE_IES, "text/plain"))],
    )
    assert response.status_code == 422
    huge = _payload()
    huge["search"]["spacingX"] = {"min": 0.5, "max": 10.0, "step": 0.05}
    huge["search"]["spacingY"] = {"min": 0.5, "max": 10.0, "step": 0.05}
    response = client.post(
        "/optimize", data={"payload": json.dumps(huge)},
        files=[("iesFiles", ("dim.ies", SAMPLE_IES, "text/plain"))],
    )
    assert response.status_code == 422
