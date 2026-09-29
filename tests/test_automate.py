"""Automate check: compliance, catalog comparison, providers, validation."""

import pytest

from app.automate import automate as run_search
from app.automate import classify_miss, frange, is_compliant, pick_diverse, shortlist_for_key
from app.automate.layouts import LayoutSpec, auto_spacing_range
from app.automate.lumen import passes_lumen_gate, required_flux, room_uf
from app.automate.search import Solution, _Row
from app.controllers.automate_controller import _fixture_provider, _standard_provider
from app.engine import RoomInput
from app.main import app
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    StandardTarget,
    spec_from_variant,
)
from app.schemas.fixtures import VariantDetailResponse
from app.schemas.automate import application_for_mounting_height
from app.schemas.standards import StandardResponse
from app.services.ies_service import installed_flux, load_ies
from app.services.variant_photometrics import (
    apply_variant_dimensions,
    scale_profile_to_lumens,
    variant_lumens,
    variant_wattage,
)
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
    # One grid per variant: a single-variant catalog yields its best grid.
    assert len(outcome.solutions) == 1
    sol = outcome.solutions[0]
    assert sol.average >= 50.0 and sol.uniformity >= 0.5
    assert sol.average <= 50.0 * 1.3  # overdesign cap respected


def test_catalog_brighter_fixture_needs_fewer_fixtures():
    space = dict(SPACE, sx_vals=[2.0, 3.0, 4.0], sy_vals=[2.0, 3.0, 4.0])  # 4m centers 1 fixture
    outcome = run_search(ROOM, {"dim": DIM, "bright": BRIGHT}, TARGET, **space,
                         top_k=6, stage_b_n=8)
    by_key: dict[str, list[int]] = {}
    for sol in outcome.solutions:
        assert is_compliant(sol.average, sol.uniformity, TARGET)
        by_key.setdefault(sol.variant_key, []).append(sol.count)
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


def _row(count: int, avg: float, u0: float = 0.6) -> _Row:
    return _Row(key="k", spec=None, placements=[], count=count, avg=avg, u0=u0)  # type: ignore[arg-type]


def test_shortlist_covers_every_count_band():
    # 12 dense "feasible" rows alone would hog a naive top-12 shortlist;
    # round-robin must still verify every intermediate count.
    feas = [_row(6, 360.0 + i) for i in range(12)]
    rest = [_row(c, 200.0) for c in (2, 3, 4, 5) for _ in range(3)]
    picked = shortlist_for_key(feas, rest, [], 12)
    assert len(picked) == 12
    assert {r.count for r in picked} == {2, 3, 4, 5, 6}
    # Round-robin: first pass touches every band, then depth increases.
    counts = [r.count for r in picked]
    assert counts[:5] == [2, 3, 4, 5, 6]
    assert counts[5:10] == [2, 3, 4, 5, 6]
    # Within a band, feas entries keep priority over rest.
    sixes = [r.avg for r in picked if r.count == 6]
    assert sixes == sorted(sixes)
    # Empty pools fall back to brightest-first.
    fallback = [_row(4, 100.0), _row(2, 300.0), _row(9, 200.0), _row(1, 50.0)]
    assert [r.count for r in shortlist_for_key([], [], fallback, 12)] == [2, 9, 4]


def test_best_per_variant_keeps_best_grid():
    from app.automate.search import best_per_variant

    def _sol(key, count, avg, u0):
        return Solution(key, LayoutSpec(sx=2, sy=2, ox=1, oy=1, rotation=0),
                        [], count, avg, 0, 0, u0, avg / 50 - 1)

    rows = [
        _sol("a", 6, 60.0, 0.8),
        _sol("a", 4, 55.0, 0.7),   # fewest fixtures wins for variant a
        _sol("a", 4, 58.0, 0.9),   # same count, higher overdesign loses
        _sol("b", 2, 52.0, 0.6),
    ]
    best = best_per_variant(rows, lambda s: s.variant_key,
                            lambda s: (s.count, s.overdesign, -s.uniformity))
    assert [(s.variant_key, s.count, s.average) for s in best] == [("a", 4, 55.0), ("b", 2, 52.0)]


def test_classify_miss_reports_first_failing_check():
    target = StandardTarget(activity_id="t", avg_lux=300.0, uniformity=0.4,
                            max_overdesign=0.3)
    assert classify_miss(250.0, 0.9, target) == "under_target"
    assert classify_miss(500.0, 0.9, target) == "over_cap"
    assert classify_miss(320.0, 0.2, target) == "uniformity"
    assert classify_miss(320.0, 0.5, target) is None
    assert classify_miss(300.0, 0.4, target) is None  # boundary compliant


def test_starvation_scenario_verifies_intermediate_counts():
    # Mirrors the real 5x5 m / 300 lx case: a bright panel where dense grids
    # overshoot and sparse grids undershoot — the compliant count-4 layouts
    # must be verified (round-robin) instead of crowded out.
    target = StandardTarget(activity_id="t", avg_lux=300.0, uniformity=0.4,
                            max_overdesign=0.3)
    profile = scale_profile_to_lumens(load_ies(SAMPLE_IES), 5280.0)
    dim = scale_profile_to_lumens(load_ies(SAMPLE_IES), 2000.0)
    room = RoomInput(polygon=[(0, 0), (5, 0), (5, 5), (0, 5)],
                     ceiling_height=4.0, mounting_height=3.0,
                     floor_zone=0.5, wall_zone=None)
    vals = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
    # Second variant too dim to ever comply: hosts the miss without
    # disturbing the bright variant's per-key budget.
    outcome = run_search(room, {"v": profile, "w": dim}, target,
                         sx_vals=vals, sy_vals=vals,
                         offset_fractions=[0.5], rotations=[0.0],
                         wattages={"v": 48.0, "w": 20.0}, lumens={"v": 5280.0, "w": 2000.0},
                         top_k=5, stage_b_n=12)
    # One grid per variant: the twin count-4 layouts collapse to a single
    # best-grid solution instead of filling the list with one variant.
    assert [s.variant_key for s in outcome.solutions] == ["v"]
    sol = outcome.solutions[0]
    assert (sol.count, sol.miss_reason) == (4, None)
    assert sol.average >= target.avg_lux and sol.uniformity >= target.uniformity
    # Heatmap retained: one maintained lux value per shared floor patch.
    assert outcome.grids is not None
    assert len(sol.floor_values) == len(outcome.grids.floor) > 0
    assert min(sol.floor_values) == pytest.approx(sol.minimum)
    assert max(sol.floor_values) == pytest.approx(sol.maximum)
    # Nearest miss from the only unshown variant, not the brightest overall.
    assert outcome.closest_miss is not None
    assert outcome.closest_miss.variant_key == "w"
    assert outcome.closest_miss.miss_reason == "under_target"
    assert outcome.closest_miss.average < target.avg_lux


def test_application_derivation_threshold():
    assert application_for_mounting_height(2.9) == "interior"
    assert application_for_mounting_height(3.0) == "interior"
    assert application_for_mounting_height(5.0) == "industrial"


def test_auto_spacing_from_room_and_mounting():
    # <= 3.0m gets 0.5m step
    lo, hi, step = auto_spacing_range(
        [(0, 0), (10, 0), (10, 8), (0, 8)], 3.0, 1.5, 2, 2000
    )
    assert lo == 1.5 and hi == pytest.approx(4.5) and step == 0.5

    # > 3.0m gets coarser 1.0m step for high/vast spaces
    lo, hi, step = auto_spacing_range(
        [(0, 0), (10, 0), (10, 8), (0, 8)], 3.2, 1.5, 2, 2000
    )
    assert lo == 1.5 and hi == pytest.approx(4.8) and step == 1.0

    # Tiny room collapses to a single spacing instead of erroring.
    assert auto_spacing_range([(0, 0), (1, 0), (1, 1), (0, 1)], 2.5, 1.5, 2, 2000) == (1.0, 1.0, 0.5)
    # Huge room widens the step to respect the candidate cap.
    lo, hi, step = auto_spacing_range(
        [(0, 0), (100, 0), (100, 60), (0, 60)], 3.0, 1.5, 2, 2000
    )
    assert hi == 4.5
    assert len(frange(lo, hi, step)) ** 2 * 2 <= 2000


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


def _variant_detail(**over):
    base = {
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
        "fixture": {
            "id": "22222222-2222-4222-8222-222222222222",
            "manufacturer_name": "M", "name": "F", "is_main_solution": True,
            "applications": ["interior"],
            "created_at": "2026-09-22T10:00:00Z",
            "updated_at": "2026-09-22T10:00:00Z",
        },
    }
    return VariantDetailResponse.model_validate(base | over)


def test_fixture_geometries_mirror_engine_fixtures():
    from app.domain.models import Fixture
    from app.services.fixture_service import fixture_geometries

    profile = load_ies(SAMPLE_IES)
    fixtures = [
        Fixture(id="F1", position=(1.0, 2.0, 2.9), aim_direction=(0.0, 0.0, -1.0),
                rotation=90.0, ies_profile=profile),
    ]
    geo = fixture_geometries(fixtures)
    assert len(geo) == 1
    g = geo[0]
    assert g.id == "F1" and g.position == (1.0, 2.0, 2.9) and g.rotation == 90.0
    assert (g.length, g.width, g.height) == (profile.length, profile.width, profile.height)
    assert len(g.corners) == 4 and len(g.elements) >= 1


def test_spec_from_variant_converts_mm_to_meters():
    spec = spec_from_variant(
        _variant_detail(dimension_length="600", dimension_width="600",
                        dimension_depth="20", dimension_radius=None),
        SAMPLE_IES,
    )
    assert (spec.length, spec.width, spec.height) == (0.6, 0.6, 0.02)
    # Round opening: radius doubles to a square when length/width absent.
    spec = spec_from_variant(_variant_detail(dimension_radius="100"), SAMPLE_IES)
    assert (spec.length, spec.width, spec.height) == (0.2, 0.2, None)
    # Nothing sent -> all None -> pure IES fallback downstream.
    spec = spec_from_variant(_variant_detail(), SAMPLE_IES)
    assert (spec.length, spec.width, spec.height) == (None, None, None)


def test_apply_variant_dimensions_overrides_per_axis():
    profile = load_ies(SAMPLE_IES)
    out = apply_variant_dimensions(profile, 0.6, None, 0.02)
    assert out.length == 0.6 and out.height == 0.02
    assert out.width == profile.width  # untouched axis keeps IES value
    assert out.flux_scale == profile.flux_scale  # ratings untouched
    assert apply_variant_dimensions(profile, None, None, None) == profile
    assert apply_variant_dimensions(profile, 0.0, -1.0, None) == profile


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
        applications=("interior",),
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
        # mountingHeight 3.0 -> interior; IES shape from SAMPLE_IES but rating
        # from the variant (20W x 150 lm/W = 3000 lm, rescaled in controller).
        response = client.post("/automate", json=_payload(variantIds=["var-bright"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["target"]["avgLux"] == 50
        assert body["solutions"]
        assert all(s["variantId"] == "var-bright" for s in body["solutions"])
        assert all(s["powerW"] == s["fixtureCount"] * 20.0 for s in body["solutions"])
        # Placements are fully resolved world coordinates: z = mounting
        # height, tilt 0 (downlights); no iesRef/aimDirection keys at all.
        for s in body["solutions"]:
            assert s["placements"]
            for p in s["placements"]:
                assert p["z"] == 3.0
                assert p["tiltAngle"] == 0.0
                assert "iesRef" not in p and "aimDirection" not in p
            # Engine fixtures for visualization: one per placed fixture,
            # opening corners, luminous-plane z, no aim vector.
            assert len(s["fixtures"]) == s["fixtureCount"]
            for fx in s["fixtures"]:
                assert len(fx["corners"]) == 4 and len(fx["elements"]) >= 1
                assert 0 < fx["position"]["z"] <= 3.0
                assert fx["tiltAngle"] == 0.0
                assert "aimDirection" not in fx
            # Heatmap: values order-match the shared floor patches once.
            assert s["totalFloor"] is not None
            assert len(s["totalFloor"]["values"]) == len(body["floorPatches"]) > 0
            assert min(s["totalFloor"]["values"]) == pytest.approx(s["minimum"])
            assert max(s["totalFloor"]["values"]) == pytest.approx(s["maximum"])
        assert body["closestMiss"] is None or body["closestMiss"]["totalFloor"] is None
        for key in ("spacing", "nx", "ny", "border", "workPlaneHeight"):
            assert key in body["floorMeta"]
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
            "var-industrial": _spec(
                "var-industrial", wattage=10.0, lumens=1000.0,
                applications=("industrial",),
            ),
        }
    )
    try:
        client = TestClient(app)
        # mountingHeight 3.0 -> interior; no variantIds -> auto-list.
        response = client.post("/automate", json=_payload())
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["solutions"]
        assert {s["variantId"] for s in body["solutions"]} <= {"var-dim", "var-bright"}
    finally:
        app.dependency_overrides.clear()


def test_automate_endpoint_auto_spacing_when_omitted():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {
            "var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0),
            "var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0),
        }
    )
    try:
        client = TestClient(app)
        payload = _payload(variantIds=["var-bright"])
        del payload["search"]  # no spacing -> server auto from room + mounting
        response = client.post("/automate", json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["appliedSpacingX"]["max"] == 4.0  # min(SHR 4.5, room 4)
        assert body["appliedSpacingX"]["min"] == 1.5
        assert body["solutions"]
    finally:
        app.dependency_overrides.clear()


def test_automate_echoes_application_and_overdesign_override():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {
            "var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0),
            "var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0),
        }
    )
    try:
        client = TestClient(app)
        # mountingHeight 3.0 -> interior under the <= rule.
        response = client.post("/automate", json=_payload(variantIds=["var-bright"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["application"] == "interior"
        assert body["target"]["maxOverdesign"] == 0.3
        # Relaxed cap is echoed and enforced on every solution.
        response = client.post(
            "/automate", json=_payload(variantIds=["var-bright"], maxOverdesign=1.0)
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["target"]["maxOverdesign"] == 1.0
        assert body["solutions"]
        rec = [s for s in body["solutions"] if s["recommended"]]
        flag = [s for s in body["solutions"] if not s["recommended"]]
        assert rec, "compliant picks come first"
        assert all(s["overdesign"] <= 1.0 for s in rec)
        assert all(s["missReason"] == "over_cap" and s["overdesign"] > 1.0 for s in flag)
        assert len(body["solutions"]) <= 4  # topK bound holds with filler
        # Negative cap rejected.
        assert client.post(
            "/automate", json=_payload(variantIds=["var-bright"], maxOverdesign=-0.1)
        ).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_variant_appears_at_most_once_across_response():
    # Structural rule: a variant shown once (solution or flagged) never
    # reappears as over-cap pick or miss.
    space = dict(SPACE, sx_vals=[2.0, 3.0, 4.0], sy_vals=[2.0, 3.0, 4.0])
    outcome = run_search(ROOM, {"dim": DIM, "bright": BRIGHT}, TARGET, **space,
                         top_k=6, stage_b_n=8)
    shown = [s.variant_key for s in outcome.solutions + outcome.overcap]
    if outcome.closest_miss is not None:
        shown.append(outcome.closest_miss.variant_key)
    assert len(set(shown)) == len(shown)
    assert shown, "expected at least one entry"


def test_automate_miss_carries_reason():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {"var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0)}
    )
    try:
        client = TestClient(app)
        # Zero tolerance: nothing fully complies, so the single variant fills
        # one flagged over-cap slot and there is no unshown variant left
        # for the miss section (miss omitted by rule).
        response = client.post(
            "/automate", json=_payload(variantIds=["var-bright"], maxOverdesign=0.0)
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["solutions"]) == 1, "one grid per variant"
        sol = body["solutions"][0]
        assert sol["recommended"] is False and sol["missReason"] == "over_cap"
        assert body["closestMiss"] is None
    finally:
        app.dependency_overrides.clear()


def test_automate_under_target_miss_is_not_recommended():
    # A too-dim variant can never comply nor over-cap: it hosts the miss,
    # which must read recommended:false with its true under_target reason
    # (the exact contradiction this guards against).
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {
            "var-bright": _spec("var-bright", wattage=20.0, lumens=3000.0),
            "var-dim": _spec("var-dim", wattage=10.0, lumens=1000.0),
            "var-tiny": _spec("var-tiny", wattage=3.0, lumens=300.0),
        }
    )
    try:
        client = TestClient(app)
        response = client.post(
            "/automate",
            json=_payload(variantIds=["var-bright", "var-dim", "var-tiny"]),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["solutions"]
        miss = body["closestMiss"]
        assert miss is not None
        assert miss["variantId"] == "var-tiny"
        assert miss["missReason"] == "under_target"
        assert miss["recommended"] is False
        assert miss["average"] < body["target"]["avgLux"]
    finally:
        app.dependency_overrides.clear()


def test_pick_overcap_only_pure_nearest_first():
    from app.automate.search import pick_overcap

def _miss(count, avg, u0, reason, sx=2.0, key="v"):
    return Solution(key, LayoutSpec(sx=sx, sy=2, ox=1, oy=1, rotation=0),
                    [], count, avg, 0, 0, u0, avg / 50 - 1, miss_reason=reason)

    target = StandardTarget(activity_id="t", avg_lux=50.0, uniformity=0.5,
                            max_overdesign=0.3)
    misses = [
        _miss(2, 80.0, 0.9, "over_cap", sx=2.0, key="a"),     # excess 30
        _miss(4, 60.0, 0.9, "over_cap", sx=3.0, key="b"),     # excess 10 -> nearest
        _miss(1, 40.0, 0.9, "under_target", sx=4.0, key="c"),  # never promoted
        _miss(3, 70.0, 0.2, "over_cap", sx=2.5, key="d"),      # u0 fails -> never promoted
    ]
    picks = pick_overcap(misses, target, 5)
    assert [(p.count, p.miss_reason) for p in picks] == [(4, "over_cap"), (2, "over_cap")]
    assert pick_overcap(misses, target, 0) == []
    assert pick_overcap(misses, target, 1)[0].count == 4


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


def test_automate_endpoint_with_variant_dimensions():
    app.dependency_overrides[_standard_provider] = _office_provider
    app.dependency_overrides[_fixture_provider] = lambda: InMemoryFixtureProvider(
        {"var-panel": _spec("var-panel", wattage=48.0, lumens=5280.0,
                            length=0.6, width=0.6, height=0.02)}
    )
    try:
        client = TestClient(app)
        response = client.post("/automate", json=_payload(variantIds=["var-panel"]))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["solutions"]
        assert all(s["variantId"] == "var-panel" for s in body["solutions"])
    finally:
        app.dependency_overrides.clear()


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


def test_resolve_max_fixtures_scales_with_area():
    from app.controllers.automate_controller import _resolve_max_fixtures
    from app.schemas.automate import AutomateRequest, SearchSpaceDto
    from app.schemas.geometry import Point2D

    # Standard office (10x10 = 100 m^2) defaults to 64
    small_req = AutomateRequest(
        activityId="office",
        polygon=[Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)],
        ceilingHeight=3.0,
        mountingHeight=2.8,
    )
    assert _resolve_max_fixtures(small_req, [(0, 0), (10, 0), (10, 10), (0, 10)]) == 64

    # Vast space (100x60 = 6,000 m^2) auto-scales to 600
    vast_req = AutomateRequest(
        activityId="warehouse",
        polygon=[Point2D(x=0, y=0), Point2D(x=100, y=0), Point2D(x=100, y=60), Point2D(x=0, y=60)],
        ceilingHeight=8.0,
        mountingHeight=7.0,
    )
    assert _resolve_max_fixtures(vast_req, [(0, 0), (100, 0), (100, 60), (0, 60)]) == 600

    # Explicit maxFixtures override wins
    explicit_req = AutomateRequest(
        activityId="warehouse",
        polygon=[Point2D(x=0, y=0), Point2D(x=100, y=0), Point2D(x=100, y=60), Point2D(x=0, y=60)],
        ceilingHeight=8.0,
        mountingHeight=7.0,
        search=SearchSpaceDto(maxFixtures=150),
    )
    assert _resolve_max_fixtures(explicit_req, [(0, 0), (100, 0), (100, 60), (0, 60)]) == 150


def test_auto_spacing_range_scales_floor_with_high_mounting():
    # 7m high-bay mounting height scales minimum spacing floor to 3.5m and step to 1.0m
    lo, hi, step = auto_spacing_range(
        [(0, 0), (100, 0), (100, 60), (0, 60)], 7.0, 1.5, 2, 2000
    )
    assert lo == 3.5
    assert hi == pytest.approx(10.5)
    assert step == 1.0


def test_resolve_rotations_and_stage_b():
    from app.controllers.automate_controller import _resolve_rotations, _resolve_stage_b
    from app.schemas.automate import AutomateRequest, SearchSpaceDto
    from app.schemas.geometry import Point2D

    poly = [Point2D(x=0, y=0), Point2D(x=10, y=0), Point2D(x=10, y=10), Point2D(x=0, y=10)]
    req = AutomateRequest(activityId="office", polygon=poly, ceilingHeight=3.0, mountingHeight=2.8)

    # Identical ranges without explicit rotation override collapse to [0.0]
    assert _resolve_rotations(req, [1.5, 2.0], [1.5, 2.0]) == [0.0]
    # Asymmetric ranges keep both rotations
    assert _resolve_rotations(req, [1.5, 2.0], [2.5, 3.0]) == [0.0, 90.0]
    # Explicit rotations override wins
    req_rot = AutomateRequest(
        activityId="office", polygon=poly, ceilingHeight=3.0, mountingHeight=2.8,
        search=SearchSpaceDto(rotations=[45.0, 90.0]),
    )
    assert _resolve_rotations(req_rot, [1.5, 2.0], [1.5, 2.0]) == [45.0, 90.0]

    # Stage-B: small space defaults to 12
    assert _resolve_stage_b(req, 100.0) == 12
    # Stage-B: vast space auto-scales to 2
    assert _resolve_stage_b(req, 6000.0) == 2
    # Stage-B: explicit override wins
    req_b = AutomateRequest(
        activityId="office", polygon=poly, ceilingHeight=3.0, mountingHeight=2.8,
        stageB=6,
    )
    assert _resolve_stage_b(req_b, 6000.0) == 6


