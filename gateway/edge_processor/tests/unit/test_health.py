from fastapi.testclient import TestClient

from app.main import build_app
from app.settings import RuntimeSettings


def test_healthz_returns_gateway_identity() -> None:
    """Verify the public health endpoint exposes gateway identity.

    :return: None. Assertions validate status code and response payload.
    """
    settings = RuntimeSettings(gateway_id="gw-test-001", app_name="edge-processor-test")
    client = TestClient(build_app(settings))

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "edge-processor-test",
        "gateway_id": "gw-test-001",
    }
