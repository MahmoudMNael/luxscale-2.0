"""Automate check: compliance, catalog comparison, providers, validation."""

import pytest

from app.automate import automate as run_search
from app.automate import frange, is_compliant, pick_diverse
from app.automate.layouts import LayoutSpec
from app.automate.lumen import passes_lumen_gate, required_flux, room_uf
from app.automate.search import Solution
from app.controllers.automate_controller import _fixture_provider, _standard_provider
from app.engine import RoomInput
from app.main import app
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    StandardTarget,
)
from app.schemas.automate import application_for_mounting_height
from app.schemas.standards import StandardResponse
from app.services.ies_service import installed_flux, load_ies
from app.services.variant_photometrics import variant_lumens, variant_wattage
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


def test_application_derivation_threshold():
    assert application_for_mounting_height(2.9) == "interior"
    assert application_for_mounting_height(3.0) == "industrial"
    assert application_for_mounting_height(5.0) == "industrial"


def test_standard_response_target_mapping():
    payload = {
        "id": "en12464_1_v2019_6_1_1",
        "qdrant_point_id": "abc",
        "standard_metadata": {
            "standard_code": "EN12464-1", "version_year": "2019", "is_latest": True,
        },
        "hierarchy": {
            "category_table_number": "6.1", "category_title": "Offices",
            "ref_number": "6.1.1", "page": 1,
        },
        "activity": "Writing, typing, reading",
        "parameters": {"em_r_lx": 500.0, "uo": 0.6},
        "specific_requirements": None,
        "searchable_text": "office writing",
        "content_hash": "hash",
        "created_at": "2026-09-22T10:00:00Z",
        "updated_at": "2026-09-22T10:00:00Z",
    }
    standard = StandardResponse.model_validate(payload)
    assert standard.target_illuminance() == 500.0
    assert standard.target_uniformity() == 0.6


def test_variant_photometrics_uses_power_times_efficacy():
    from app.schemas.fixtures import VariantResponse

    variant = VariantResponse.model_validate(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "fixture_id": "22222222-2222-4222-8222-222222222222",
            "name": "V1", "chip": "C", "driver": "D",
            "power": 20, "efficacy": 150,
            "power_factor": "0.95", "cri": "80",
            "mechanical_protections": [], "electrical_protections": [],
            "dimension_length": None, "dimension_width": None,
            "dimension_depth": None, "dimension_radius": None,
            "model_3d_file_id": None, "model_3d_file": None,
            "ies_file_id": "33333333-3333-4333-8333-333333333333",
            "ies_file": {
                "id": "33333333-3333-4333-8333-333333333333",
                "relative_path": "ies/a.ies", "original_filename": "a.ies",
                "mime_type": "text/plain", "size_bytes": 10,
                "created_at": "2026-09-22T10:00:00Z",
            },
            "images": [],
            "created_at": "2026-09-22T10:00:00Z",
            "updated_at": "2026-09-22T10:00:00Z",
        }
    )
    assert variant_wattage(variant) == 20.0
    assert variant_lumens(variant) == 3000.0  # 20W x 150 lm/W, not the IES flux


def _payload(**over):
    base = {
        "polygon": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 4}, {"x": 0, "y": 4}],
        "ceilingHeight": 3.0,
        "mountingHeight": 3.0,
        "floorZone": 0.25,
        "wallZone": 0.25,
        "activityId": "office",
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


def _spec(variant_id: str, wattage: float, lumens: float, **over) -> FixtureSpec:
    defaults = dict(
        id=variant_id,
        fixture_id="fix-1",
        variant_id=variant_id,
        ies_text=SAMPLE_IES,
        wattage=wattage,
        lumens=lumens,
        efficacy=(lumens / wattage if wattage else 0.0),
        power=wattage,
        is_main_solution=True,
        applications=("industrial",),
    )
    return FixtureSpec(**(defaults | over))


def _office_provider() -> InMemoryStandardProvider:
    return InMemoryStandardProvider(
        {"office": StandardTarget(activity_id="office", avg_lux=50, uniformity=0.5,
                                   max_overdesign=0.3)}
    )


def test_automate_endpoint_with_explicit_variant_ids():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {
            "var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0),
            "var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0),
        }
    )
    try:
        client = TestClient(app)
        # mountingHeight 3.0 -> industrial; IES shape from SAMPLE_IES but rating
        # from the variant (20W x 150 lm/W = 3000 lm, rescaled in controller).
        response = client.post("/automate", json=_payload(variantIds=["var-bright"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["target"]["avgLux"] == 50
        assert body["solutions"]
        assert all(s["fixtureId"] == "var-bright" for s in body["solutions"])
        assert all(s["powerW"] == s["fixtureCount"] * 20.0 for s in body["solutions"])
    finally:
        app.dependency_overrides.clear()


def test_automate_endpoint_auto_lists_main_variants_for_application():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {
            "var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0),
            "var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0),
            # Non-main variant must never enter the catalog (filtered).
            "var-side": _spec(
                "var-side", wattage=20.0, lumens=3000.0, is_main_solution=False,
            ),
            # Wrong-application variant must never enter the catalog either.
            "var-interior": _spec(
                "var-interior", wattage=10.0, lumens=1000.0,
                applications=("interior",),
            ),
        }
    )
    try:
        client = TestClient(app)
        # mountingHeight 3.0 -> industrial; no variantIds -> auto-list.
        response = client.post("/automate", json=_payload())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["solutions"]
        assert {s["fixtureId"] for s in body["solutions"]} <= {"var-dim", "var-bright"}
    finally:
        app.dependency_overrides.clear()


def test_provider_filters_by_application_and_main_flag():
    provider = InMemoryFixtureProvider(
        {
            "var-main": _spec("var-main", wattage=20.0, lumens=3000.0,
                              applications=("interior",)),
            "var-side": _spec("var-side", wattage=20.0, lumens=3000.0,
                              applications=("interior",), is_main_solution=False),
        }
    )
    assert [s.id for s in provider.list_main_variants("interior")] == ["var-main"]
    assert [s.id for s in provider.get_variants(["var-main"], "interior")] == ["var-main"]
    with pytest.raises(Exception):
        provider.get_variants(["var-side"], "interior")
    with pytest.raises(Exception):
        provider.get_variants(["var-main"], "industrial")


def test_automate_endpoint_rejects_non_main_variant_ids():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {"var-side": _spec("var-side", wattage=20.0, lumens=3000.0,
                           is_main_solution=False)}
    )
    try:
        client = TestClient(app)
        response = client.post("/automate", json=_payload(variantIds=["var-side"]))
        # Unknown as a main-solution industrial variant -> provider error (400/502).
        assert response.status_code in (400, 502), response.text
    finally:
        app.dependency_overrides.clear()


def test_automate_validation():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {"var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0)}
    )
    try:
        client = TestClient(app)
        # mountingHeight above ceilingHeight.
        bad = _payload(mountingHeight=4.0, ceilingHeight=3.0, variantIds=["var-dim"])
        assert client.post("/automate", json=bad).status_code == 422
        # Missing activityId.
        bad2 = _payload(variantIds=["var-dim"])
        del bad2["activityId"]
        assert client.post("/automate", json=bad2).status_code == 422
        # Oversized search space.
        huge = _payload(variantIds=["var-dim"])
        huge["search"]["spacingX"] = {"min": 0.5, "max": 10.0, "step": 0.05}
        huge["search"]["spacingY"] = {"min": 0.5, "max": 10.0, "step": 0.05}
        assert client.post("/automate", json=huge).status_code == 422
    finally:
        app.dependency_overrides.clear()
