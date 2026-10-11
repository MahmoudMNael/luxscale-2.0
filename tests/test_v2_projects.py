from __future__ import annotations

import io
import zipfile
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.modules.photometry.ldt_service import load_ldt

SAMPLE_LDT = """Company XYZ
1
1
1
0
5
0
Rep-001
Troffer 600
Lum-001
troffer.ldt
2026-10-11
600
600
80
600
600
80
80
80
80
100
100
1.0
0
1
1
LED
3600
4000
80
40
0 0 0 0 0 0 0 0 0 0
0
0 30 60 75 90
280 240 150 50 0
"""


def test_ldt_parser() -> None:
    profile = load_ldt(SAMPLE_LDT)
    assert profile is not None
    assert profile.vertical_angles == [0.0, 30.0, 60.0, 75.0, 90.0]
    assert profile.horizontal_angles == [0.0]
    assert profile.width == 0.6
    assert profile.length == 0.6
    assert len(profile.candela_table) == 5
    # Intensities scaled: 280 * (3600/1000) = 1008 cd
    assert profile.candela_table[0][0] == pytest.approx(1008.0)


def test_v2_projects_crud() -> None:
    client = TestClient(app)

    project_payload = {
        "schemaVersion": 1,
        "id": "test_v2_proj_01",
        "name": "Headquarters Level 2",
        "sceneName": "Scene 01",
        "room": {
            "polygon": [
                {"x": 0.0, "y": 0.0},
                {"x": 8.0, "y": 0.0},
                {"x": 8.0, "y": 6.0},
                {"x": 0.0, "y": 6.0},
            ],
            "ceilingHeight": 3.0,
            "wallThickness": 0.2,
            "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2},
            "obstructions": [],
        },
        "fixtures": [
            {
                "id": "#L-01",
                "name": "Troffer 1",
                "assetId": "asset-troffer-01",
                "position": {"x": 2.0, "y": 2.0, "z": 2.8},
                "rotation": 0.0,
                "tiltAngle": 0.0,
                "aimVector": {"x": 0.0, "y": 0.0, "z": -1.0},
                "luminousFlux": 3600.0,
                "wattage": 40.0,
                "cct": 4000,
                "fluxMultiplier": 1.0,
            }
        ],
        "patterns": [],
        "workplanes": [{"id": "WP-01", "name": "Task", "height": 0.85, "margin": 0.5}],
        "physics": {"maintenanceFactor": 0.8, "radiosity": True},
        "compliance": {
            "standardId": "EN 12464-1 (OFFICE)",
            "targetLux": 500.0,
            "targetUniformity": 0.6,
            "maxOverdesign": 0.3,
        },
        "assets": [],
    }

    # 1. Create project
    res_create = client.post("/api/v2/projects", json=project_payload)
    assert res_create.status_code == 201, res_create.text
    created = res_create.json()
    assert created["id"] == "test_v2_proj_01"
    assert created["name"] == "Headquarters Level 2"

    # 2. List projects
    res_list = client.get("/api/v2/projects")
    assert res_list.status_code == 200
    items = res_list.json()
    assert any(p["id"] == "test_v2_proj_01" for p in items)

    # 3. Get single project
    res_get = client.get("/api/v2/projects/test_v2_proj_01")
    assert res_get.status_code == 200
    doc = res_get.json()
    assert len(doc["fixtures"]) == 1

    # 4. Export .lxsc zip
    res_export = client.get("/api/v2/projects/test_v2_proj_01/export")
    assert res_export.status_code == 200
    assert res_export.headers["content-type"] == "application/zip"
    zip_bytes = res_export.content

    # Verify zip content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        assert "project.json" in zf.namelist()

    # 5. Import .lxsc zip
    import_payload = {"file": ("imported.lxsc", zip_bytes, "application/zip")}
    res_import = client.post("/api/v2/projects/import", files=import_payload)
    assert res_import.status_code == 201
    imported_doc = res_import.json()
    assert imported_doc["id"] == "test_v2_proj_01"

    # 6. Delete project
    res_del = client.delete("/api/v2/projects/test_v2_proj_01")
    assert res_del.status_code == 204

    # Verify 404 after delete
    res_get_del = client.get("/api/v2/projects/test_v2_proj_01")
    assert res_get_del.status_code == 404
