"""Tests for V2 multi-workplane radiosity calculation and pattern resolution."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.v2.pattern_resolver_service import (
    ParametricPatternDto,
    PatternSlotOverride,
    resolve_pattern,
)

client = TestClient(app)


def test_resolve_pattern_grid_and_staggered():
    poly = [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]
    grid_pat = ParametricPatternDto(
        id="PAT_GRID",
        name="Grid Array",
        type="grid",
        grid_type="count",
        count_x=3,
        count_y=2,
        mount_height=2.8,
        base_rotation=45.0,
        base_tilt=10.0,
    )
    placements = resolve_pattern(grid_pat, poly, default_mount_height=2.8)
    assert len(placements) == 6
    for p in placements:
        assert p.z == 2.8
        assert p.rotation == 45.0

    # Test with slot override
    grid_pat.slotOverrides["r0_c0"] = PatternSlotOverride(
        rotation_offset=15.0,
        disabled=False,
    )
    grid_pat.slotOverrides["r1_c1"] = PatternSlotOverride(disabled=True)
    placements_overridden = resolve_pattern(grid_pat, poly, default_mount_height=2.8)
    assert len(placements_overridden) == 5  # One slot disabled
    p0 = next(p for p in placements_overridden if p.id == "PAT_GRID_1")
    assert p0.rotation == 60.0  # 45 + 15


def test_resolve_pattern_linear_and_circumference():
    poly = [(0.0, 0.0), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]
    linear_pat = ParametricPatternDto(
        id="PAT_LINE",
        name="Linear Array",
        type="linear",
        line_start={"x": 1.0, "y": 3.0},
        line_end={"x": 7.0, "y": 3.0},
        count=4,
        mount_height=2.8,
    )
    linear_placements = resolve_pattern(linear_pat, poly, default_mount_height=2.8)
    assert len(linear_placements) == 4
    assert linear_placements[0].x == 1.0
    assert linear_placements[-1].x == 7.0

    circ_pat = ParametricPatternDto(
        id="PAT_CIRC",
        name="Perimeter Array",
        type="circumference",
        wall_offset=0.8,
        perimeter_spacing=2.5,
        mount_height=2.8,
    )
    circ_placements = resolve_pattern(circ_pat, poly, default_mount_height=2.8)
    assert len(circ_placements) >= 4
    for p in circ_placements:
        assert 0.0 < p.x < 8.0
        assert 0.0 < p.y < 6.0


def test_v2_calculate_multi_workplane_and_patterns():
    request_data = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 4.0},
            {"x": 0.0, "y": 4.0},
        ],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,
        "patterns": [
            {
                "id": "GRID_01",
                "name": "Main Grid",
                "type": "grid",
                "gridType": "count",
                "countX": 2,
                "countY": 2,
                "mountHeight": 2.8,
                "baseRotation": 0.0,
                "baseTilt": 0.0,
            }
        ],
        "workplanes": [
            {
                "id": "WP-DESK",
                "name": "Desk Level",
                "height": 0.85,
                "margin": 0.5,
                "targetLux": 500,
                "targetUniformity": 0.6,
            },
            {
                "id": "WP-FLOOR",
                "name": "Floor Level",
                "height": 0.0,
                "margin": 0.2,
                "targetLux": 300,
            },
        ],
        "bounces": 1,
    }

    resp = client.post("/api/v2/calculate", json=request_data)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "workplaneResults" in data
    assert "WP-DESK" in data["workplaneResults"]
    assert "WP-FLOOR" in data["workplaneResults"]

    desk = data["workplaneResults"]["WP-DESK"]
    floor = data["workplaneResults"]["WP-FLOOR"]

    assert desk["height"] == 0.85
    assert floor["height"] == 0.0
    assert desk["evaluation"]["average"] > 0
    assert floor["evaluation"]["average"] > 0
    assert len(data["fixtures"]) == 4
    assert data["totalPowerWatts"] > 0


def test_v2_catalog_endpoints():
    resp_variants = client.get("/api/v2/catalog/variants")
    assert resp_variants.status_code == 200
    variants = resp_variants.json()
    assert isinstance(variants, list)
    assert len(variants) > 0
    assert "name" in variants[0]
    assert "power" in variants[0]

    resp_standards = client.get("/api/v2/catalog/standards?limit=5")
    assert resp_standards.status_code == 200
    res = resp_standards.json()
    assert res.get("success") is True
    standards = res.get("data", [])
    assert isinstance(standards, list)
    assert len(standards) >= 1
    assert "activity" in standards[0]
    assert "parameters" in standards[0]

    # Test IES fetch for the first variant
    first_vid = variants[0]["id"]
    resp_ies = client.get(f"/api/v2/catalog/variants/{first_vid}/ies")
    assert resp_ies.status_code == 200
    ies_data = resp_ies.json()
    assert ies_data["variantId"] == first_vid
    assert "IESNA" in ies_data["iesText"] or "TILT=" in ies_data["iesText"]


def test_v2_calculate_deduplicates_overlapping_fixtures_and_patterns():
    # Pass 4 fixtures that match the 2x2 grid from patterns
    pattern = {
        "id": "GRID_01",
        "name": "Main Grid",
        "type": "grid",
        "gridType": "count",
        "countX": 2,
        "countY": 2,
        "mountHeight": 2.8,
        "baseRotation": 0.0,
        "baseTilt": 0.0,
    }
    # Resolve what those 4 positions are for poly [0,0] to [6,4]
    # countX=2, countY=2, autoCenter => x=[1.5, 4.5], y=[1.0, 3.0]
    fixtures = [
        {"id": "F1", "x": 1.5, "y": 1.0, "z": 2.8},
        {"id": "F2", "x": 4.5, "y": 1.0, "z": 2.8},
        {"id": "F3", "x": 1.5, "y": 3.0, "z": 2.8},
        {"id": "F4", "x": 4.5, "y": 3.0, "z": 2.8},
    ]
    request_data = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 4.0},
            {"x": 0.0, "y": 4.0},
        ],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,
        "fixtures": fixtures,
        "patterns": [pattern],
        "workplanes": [
            {
                "id": "WP-DESK",
                "name": "Desk Level",
                "height": 0.85,
                "margin": 0.5,
                "targetLux": 500,
            }
        ],
    }
    resp = client.post("/api/v2/calculate", json=request_data)
    assert resp.status_code == 200
    data = resp.json()
    # Must NOT double fixtures: exactly 4 fixtures evaluated
    assert len(data["fixtures"]) == 4


def test_v2_calculate_scales_ies_to_target_lumens_and_handles_assets():
    from app.controllers.v2.calculate_controller import _get_fixture_provider
    from app.providers import FixtureSpec, InMemoryFixtureProvider
    from tests.ies_sample import ies_with

    # Base IES with 1.2m x 0.3m dimensions and 1000 lm base
    base_ies = ies_with(lumens=1000.0, length=1.2, width=0.3, height=0.08)

    # 1. Base unscaled reference (1000 lm, 40W default)
    base_request = {
        "polygon": [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 5.0}, {"x": 0.0, "y": 5.0}],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,
        "fixtures": [{"id": "F1", "x": 2.5, "y": 2.5, "iesRef": "base.ies"}],
        "assets": {"base.ies": base_ies},
        "workplanes": [{"id": "WP-01", "height": 0.85, "margin": 0.5}],
        "bounces": 0,
    }
    base_resp = client.post("/api/v2/calculate", json=base_request)
    assert base_resp.status_code == 200
    base_avg = base_resp.json()["workplaneResults"]["WP-01"]["evaluation"]["average"]

    # 2. SC-Admin catalog fixture with 30W, 150 lm/W => target lumens = 4500 lm (4.5x base)
    spec = FixtureSpec(
        id="var-4500",
        fixture_id="fix-4500",
        variant_id="var-4500",
        ies_text=base_ies,
        wattage=30.0,
        lumens=4500.0,
        power=30.0,
        efficacy=150.0,
        length=1.2,
        width=0.3,
        height=0.08,
        is_main_solution=True,
    )
    fix_prov = InMemoryFixtureProvider({spec.id: spec})
    app.dependency_overrides[_get_fixture_provider] = lambda: fix_prov

    try:
        # A: Fetch via variantId directly (no assets provided)
        req_a = {
            "polygon": [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 5.0}, {"x": 0.0, "y": 5.0}],
            "ceilingHeight": 3.0,
            "mountingHeight": 2.8,
            "fixtures": [{"id": "F1", "x": 2.5, "y": 2.5, "variantId": "var-4500"}],
            "workplanes": [{"id": "WP-01", "height": 0.85, "margin": 0.5}],
            "bounces": 0,
        }
        resp_a = client.post("/api/v2/calculate", json=req_a)
        assert resp_a.status_code == 200, resp_a.text
        data_a = resp_a.json()
        assert data_a["totalPowerWatts"] == 30.0
        assert data_a["fixtures"][0]["length"] == pytest.approx(1.2)
        assert data_a["fixtures"][0]["width"] == pytest.approx(0.3)
        avg_a = data_a["workplaneResults"]["WP-01"]["evaluation"]["average"]
        assert avg_a == pytest.approx(base_avg * 4.5, rel=1e-3)

        # B: Fetch via variantId WITH assets provided (e.g. Studio caching raw IES)
        req_b = {
            "polygon": [{"x": 0.0, "y": 0.0}, {"x": 5.0, "y": 0.0}, {"x": 5.0, "y": 5.0}, {"x": 0.0, "y": 5.0}],
            "ceilingHeight": 3.0,
            "mountingHeight": 2.8,
            "fixtures": [{"id": "F1", "x": 2.5, "y": 2.5, "variantId": "var-4500"}],
            "assets": {"var-4500": base_ies},
            "workplanes": [{"id": "WP-01", "height": 0.85, "margin": 0.5}],
            "bounces": 0,
        }
        resp_b = client.post("/api/v2/calculate", json=req_b)
        assert resp_b.status_code == 200, resp_b.text
        data_b = resp_b.json()
        assert data_b["totalPowerWatts"] == 30.0
        assert data_b["fixtures"][0]["length"] == pytest.approx(1.2)
        assert data_b["fixtures"][0]["width"] == pytest.approx(0.3)
        avg_b = data_b["workplaneResults"]["WP-01"]["evaluation"]["average"]
        assert avg_b == pytest.approx(base_avg * 4.5, rel=1e-3)
        assert avg_b == pytest.approx(avg_a, rel=1e-5)
    finally:
        app.dependency_overrides.clear()


def test_v2_calculate_with_grid_pattern_and_custom_uploaded_ies_fixture():
    from app.controllers.v2.calculate_controller import _get_fixture_provider
    from app.providers import FixtureSpec, InMemoryFixtureProvider
    from tests.ies_sample import ies_with

    catalog_ies = ies_with(lumens=2000.0, length=0.6, width=0.6, height=0.08)
    custom_ies = ies_with(lumens=1500.0, length=0.4, width=0.4, height=0.05)

    catalog_spec = FixtureSpec(
        id="var-catalog-grid",
        fixture_id="fix-grid",
        variant_id="var-catalog-grid",
        ies_text=catalog_ies,
        wattage=25.0,
        lumens=2000.0,
        power=25.0,
        efficacy=80.0,
        length=0.6,
        width=0.6,
        height=0.08,
        is_main_solution=True,
    )
    fix_prov = InMemoryFixtureProvider({catalog_spec.id: catalog_spec})
    app.dependency_overrides[_get_fixture_provider] = lambda: fix_prov

    try:
        req = {
            "polygon": [{"x": 0.0, "y": 0.0}, {"x": 6.0, "y": 0.0}, {"x": 6.0, "y": 4.0}, {"x": 0.0, "y": 4.0}],
            "ceilingHeight": 3.0,
            "mountingHeight": 2.8,
            "patterns": [
                {
                    "id": "GRID_01",
                    "name": "Grid Array",
                    "type": "grid",
                    "variantId": "var-catalog-grid",
                    "gridType": "count",
                    "countX": 2,
                    "countY": 2,
                    "mountHeight": 2.8,
                }
            ],
            "fixtures": [
                {
                    "id": "CUSTOM_F1",
                    "x": 3.0,
                    "y": 2.0,
                    "z": 2.8,
                    "variantId": "custom-ies-1793007463044-eleg",
                    "iesRef": "custom-ies-1793007463044-eleg",
                }
            ],
            "assets": {
                "custom-ies-1793007463044-eleg": custom_ies,
            },
            "workplanes": [{"id": "WP-01", "height": 0.85, "margin": 0.5}],
            "bounces": 0,
        }
        resp = client.post("/api/v2/calculate", json=req)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["fixtures"]) == 5  # 4 from grid + 1 custom
        assert data["workplaneResults"]["WP-01"]["evaluation"]["average"] > 0
    finally:
        app.dependency_overrides.clear()


