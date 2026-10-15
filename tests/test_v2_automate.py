"""Tests for V2 Automate Lighting Study background jobs and endpoints."""

from __future__ import annotations

import time
import pytest
from fastapi.testclient import TestClient

from app.controllers.v2.automate_controller import _fixture_provider, _standard_provider
from app.main import app
from app.providers import (
    FixtureSpec,
    InMemoryFixtureProvider,
    InMemoryStandardProvider,
    StandardTarget,
)
from tests.ies_sample import SAMPLE_IES

client = TestClient(app)

SAMPLE_FIXTURE = FixtureSpec(
    id="var-01",
    fixture_id="fix-01",
    variant_id="var-01",
    ies_text=SAMPLE_IES,
    wattage=30.0,
    lumens=3600.0,
    length=0.6,
    width=0.6,
    height=0.08,
)

SAMPLE_NON_MAIN_OUTDOOR_FIXTURE = FixtureSpec(
    id="var-outdoor-nonmain",
    fixture_id="fix-02",
    variant_id="var-outdoor-nonmain",
    ies_text=SAMPLE_IES,
    wattage=50.0,
    lumens=5000.0,
    length=0.8,
    width=0.4,
    height=0.1,
    is_main_solution=False,
    applications=("outdoor",),
)

SAMPLE_STANDARD = StandardTarget(
    activity_id="office_general",
    avg_lux=50.0,
    uniformity=0.4,
    max_overdesign=0.5,
)


@pytest.fixture(autouse=True)
def _override_providers():
    fp = InMemoryFixtureProvider({
        "var-01": SAMPLE_FIXTURE,
        "var-outdoor-nonmain": SAMPLE_NON_MAIN_OUTDOOR_FIXTURE,
    })
    sp = InMemoryStandardProvider({"office_general": SAMPLE_STANDARD})
    app.dependency_overrides[_fixture_provider] = lambda: fp
    app.dependency_overrides[_standard_provider] = lambda: sp
    yield
    app.dependency_overrides.clear()


def test_v2_automate_job_lifecycle_auto_grid():
    payload = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 6.0},
            {"x": 0.0, "y": 6.0},
        ],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,
        "targetLux": 50.0,
        "targetUniformity": 0.4,
        "maxOverdesign": 0.5,
        "topK": 3,
    }

    # 1. Post job
    res = client.post("/api/v2/automate/jobs", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert "jobId" in data
    assert data["status"] in ("pending", "running", "completed")
    job_id = data["jobId"]

    # 2. Poll job status
    poll_res = client.get(f"/api/v2/automate/jobs/{job_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["jobId"] == job_id
    assert poll_data["status"] == "completed"
    assert poll_data["result"] is not None
    assert len(poll_data["result"]["solutions"]) == 1

    sol0 = poll_data["result"]["solutions"][0]
    assert sol0["fixtureCount"] >= 1
    assert len(sol0["placements"]) == sol0["fixtureCount"]
    assert sol0["average"] > 0
    assert "points" in sol0
    assert len(sol0["points"]) > 0

    sol0 = poll_data["result"]["solutions"][0]
    pt0 = sol0["points"][0]
    assert "x" in pt0 and "y" in pt0 and "z" in pt0 and "lux" in pt0
    assert isinstance(pt0["lux"], (int, float))


def test_v2_automate_job_lifecycle_constrained_grid():
    payload = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 6.0},
            {"x": 0.0, "y": 6.0},
        ],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,
        "targetLux": 50.0,
        "targetUniformity": 0.4,
        "gridSpec": {
            "spacingX": 2.5,
            "spacingY": 2.5,
            "rotation": 0.0,
            "offsetFraction": 0.5,
        },
        "topK": 2,
    }

    res = client.post("/api/v2/automate/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["jobId"]

    poll_res = client.get(f"/api/v2/automate/jobs/{job_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["status"] == "completed"
    assert poll_data["result"]["appliedSpacingX"]["min"] == 2.5
    assert poll_data["result"]["appliedSpacingY"]["min"] == 2.5


def test_v2_automate_job_not_found():
    res = client.get("/api/v2/automate/jobs/nonexistent-uuid")
    assert res.status_code == 404


def test_v2_automate_bypasses_main_and_application_when_variant_ids_specified():
    payload = {
        "polygon": [
            {"x": 0.0, "y": 0.0},
            {"x": 6.0, "y": 0.0},
            {"x": 6.0, "y": 6.0},
            {"x": 0.0, "y": 6.0},
        ],
        "ceilingHeight": 3.0,
        "mountingHeight": 2.8,  # Derived app would normally be "interior"
        "variantIds": ["var-outdoor-nonmain"],  # Non-main & outdoor
        "targetLux": 50.0,
        "targetUniformity": 0.4,
        "topK": 2,
    }

    res = client.post("/api/v2/automate/jobs", json=payload)
    assert res.status_code == 202
    job_id = res.json()["jobId"]

    poll_res = client.get(f"/api/v2/automate/jobs/{job_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["status"] == "completed"
    assert len(poll_data["result"]["solutions"]) >= 1
    assert poll_data["result"]["solutions"][0]["variantId"] == "var-outdoor-nonmain"

