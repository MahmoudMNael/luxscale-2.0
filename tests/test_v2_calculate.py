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

    resp_standards = client.get("/api/v2/catalog/standards")
    assert resp_standards.status_code == 200
    standards = resp_standards.json()
    assert isinstance(standards, list)
    assert len(standards) >= 5
    assert "targetLux" in standards[0]
    assert "targetUniformity" in standards[0]
    assert any("Corridors" in s["name"] or "12464" in s["name"] for s in standards)

    # Test IES fetch for the first variant
    first_vid = variants[0]["id"]
    resp_ies = client.get(f"/api/v2/catalog/variants/{first_vid}/ies")
    assert resp_ies.status_code == 200
    ies_data = resp_ies.json()
    assert ies_data["variantId"] == first_vid
    assert "IESNA" in ies_data["iesText"] or "TILT=" in ies_data["iesText"]

