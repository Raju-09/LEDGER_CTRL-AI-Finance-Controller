import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.schema import init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_generate_and_reconcile():
    # 1. Generate a small batch
    response = client.post("/api/batches/generate", json={"n": 20, "split": "dev", "seed": 42})
    assert response.status_code == 200
    data = response.json()
    assert "batch_id" in data
    batch_id = data["batch_id"]

    # 2. Reconcile the batch (without LLM for speed and determinism)
    response = client.post(f"/api/batches/{batch_id}/reconcile", json={"use_llm": False})
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "precision" in data["metrics"]

    # 3. Check batch list
    response = client.get("/api/batches")
    assert response.status_code == 200
    assert len(response.json()) > 0

    # 4. Check specific batch
    response = client.get(f"/api/batches/{batch_id}")
    assert response.status_code == 200
    assert response.json()["id"] == batch_id

    # 5. Check matches
    response = client.get(f"/api/batches/{batch_id}/matches")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # 6. Check exceptions
    response = client.get(f"/api/batches/{batch_id}/exceptions?min_amount=0")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
