from fastapi.testclient import TestClient

from service.api import app


def test_web_home_serves_dashboard() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Web Tester" in response.text
