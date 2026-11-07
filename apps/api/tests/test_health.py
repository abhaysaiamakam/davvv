from fastapi import status


def test_health_check(client):
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "CropLens API"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data

