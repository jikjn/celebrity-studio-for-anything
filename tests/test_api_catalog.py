from __future__ import annotations

from fastapi.testclient import TestClient

from celebrity_studio.api_server import create_app


def test_model_catalog_contains_key_and_model_fields() -> None:
    client = TestClient(create_app())
    response = client.get("/api/provider/model-catalog")
    assert response.status_code == 200

    payload = response.json()
    assert "provider_types" in payload
    assert payload.get("model_input", {}).get("mode") == "freeform"
    assert payload.get("runtime_payload_fields", {}).get("providers[].api_key")
    assert payload.get("runtime_payload_fields", {}).get("providers[].model")

    ids = []
    for item in payload["provider_types"]:
        assert "id" in item
        assert "requires_api_key" in item
        ids.append(item["id"])

    assert "flowith" not in ids
