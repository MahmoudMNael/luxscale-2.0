import json

from fastapi.testclient import TestClient

from app.main import app
from tests.ies_sample import SAMPLE_IES

client = TestClient(app)

PAYLOAD = {
    "polygon": [{"x": 0, "y": 0}, {"x": 4, "y": 0}, {"x": 4, "y": 4}, {"x": 0, "y": 4}],
    "height": 3,
    "grid": {
        "x": {"spacing": 2, "offsetBeginning": 1, "offsetEnding": 1},
        "y": {"spacing": 2, "offsetBeginning": 1, "offsetEnding": 1},
    },
}


def test_calculate_200():
    response = client.post(
        "/calculate",
        data={"payload": json.dumps(PAYLOAD)},
        files={"iesFile": ("lamp.ies", SAMPLE_IES, "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.headers.get("X-Request-ID")
    body = response.json()
    assert body["fixtures"]
    fixture = body["fixtures"][0]
    assert fixture["id"]
    assert len(fixture["corners"]) == 4
    assert len(fixture["elements"]) == 1
    assert fixture["length"] == 0
    assert fixture["width"] == 0
    assert body["totalFloorIlluminance"]["values"]
    assert max(body["totalFloorIlluminance"]["values"]) > 0


def test_validation_422():
    bad = {**PAYLOAD, "height": 0}
    response = client.post(
        "/calculate",
        data={"payload": json.dumps(bad)},
        files={"iesFile": ("lamp.ies", SAMPLE_IES, "text/plain")},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["requestId"]
    assert error["details"]


def test_ies_parse_400():
    response = client.post(
        "/calculate",
        data={"payload": json.dumps(PAYLOAD)},
        files={"iesFile": ("lamp.ies", "TILT=INCLUDE\n", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IES_PARSE"


def test_openapi_has_error_schema_and_payload_ref():
    schema = app.openapi()
    post = schema["paths"]["/calculate"]["post"]
    assert "400" in post["responses"]
    assert "422" in post["responses"]
    assert "500" in post["responses"]
    assert "CalculateRequest" in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]
    payload = post["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"]["payload"]
    assert payload["$ref"].endswith("CalculateRequest")


def test_demo_page_served():
    response = client.get("/demo/")
    assert response.status_code == 200
    assert b"LuxScale" in response.content
