import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import joblib
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.runtime import Runtime
from backend.app.security import hash_password
from backend.app.store import Store
from backend.ml.anomaly import Anomaly
from backend.ml.train import train


def collection(now):
    return [{"device_id": "sentinel-x-01", "boot_id": "boot", "sequence": i,
             "uptime_ms": i*1000, "received_at": (now-timedelta(seconds=29-i)).isoformat(),
             "temperature": 24.0+i%3/10, "humidity": 48.0+i%4/10, "gas": 130+i%5,
             "presence": False, "source": "physical", "timestamp": None, "replayed": False,
             "sensor_status": {"dht22": "ok", "mq2": "ok", "pir": "ok"},
             "sensor_age_ms": {"dht22": 0, "mq2": 0, "pir": 0}} for i in range(30)]


def test_model_persistence_and_physical_inference(tmp_path):
    now = datetime.now(timezone.utc)
    rows = collection(now)
    path = tmp_path/"model.joblib"
    artifact = train(rows, path, now)
    assert artifact["samples"] == 30 and artifact["training_source"] == "physical"
    assert joblib.load(path)["trained_at"] == now.isoformat()
    detector = Anomaly(path)
    result = detector.evaluate(rows[-1])
    assert result["score"] is not None
    detector.install(artifact)
    assert detector.states["sentinel-x-01"]["score"] is None


@pytest.mark.parametrize("issue", ["short", "stale", "replayed", "invalid", "boot", "gap", "source", "sequence"])
def test_invalid_reference_preserves_model(tmp_path, issue):
    now = datetime.now(timezone.utc)
    rows = collection(now)
    path = tmp_path/"model.joblib"
    train(rows, path, now)
    before = path.read_bytes()
    if issue == "short": rows.pop(0)
    elif issue == "stale": now += timedelta(seconds=4)
    elif issue == "replayed": rows[10]["replayed"] = True
    elif issue == "invalid": rows[10]["sensor_status"]["mq2"] = "warming_up"
    elif issue == "boot": rows[10]["boot_id"] = "other"
    elif issue == "gap": rows[10]["uptime_ms"] += 2500
    elif issue == "source": rows[10]["source"] = "simulated"
    elif issue == "sequence": rows[10]["sequence"] = 3
    with pytest.raises(ValueError): train(rows, path, now)
    assert path.read_bytes() == before


def test_failed_save_preserves_model(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    path = tmp_path/"model.joblib"
    train(collection(now), path, now)
    before = path.read_bytes()
    def fail(*args): raise OSError("disk full")
    monkeypatch.setattr(joblib, "dump", fail)
    with pytest.raises(OSError): train(collection(now), path, now)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_retrain_api_security_success_and_busy(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path/'test.db'}", model_path=str(tmp_path/'model.joblib'),
                        password_hash=hash_password("password"), vision_token="secret",
                        origins=("https://testserver",), static_path="absent")
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        endpoint = "/api/v1/model/retrain"
        assert client.post(endpoint).status_code == 401
        assert client.post(endpoint, headers={"Authorization": "Bearer secret"}).status_code == 401
        login = client.post("/api/v1/login", headers={"Origin": "https://testserver"},
                            json={"username": "operateur", "password": "password"})
        headers = {"Origin": "https://testserver", "X-CSRF-Token": login.json()["csrf_token"]}
        assert client.post(endpoint).status_code == 403
        assert client.post(endpoint, headers=headers).status_code == 409
        runtime = app.state.runtime
        now = datetime.now(timezone.utc)
        rows = collection(now)
        for row in rows: runtime.store.insert_measurement(row)
        import time
        runtime.devices[settings.physical_device] = {"seen": time.monotonic(), "latest": deepcopy(rows[-1])}
        response = client.post(endpoint, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["samples"] == 30
        assert client.get("/api/v1/status").json()["model"]
        assert Path(settings.model_path).exists()
        async def concurrent():
            async with runtime.training_lock:
                with pytest.raises(ValueError, match="déjà"): await runtime.retrain()
        asyncio.run(concurrent())


def test_legacy_data_removed_without_losing_physical_history(tmp_path):
    store = Store(f"sqlite:///{tmp_path/'history.db'}")
    store.initialize()
    rows = collection(datetime.now(timezone.utc))
    store.insert_measurement(rows[0])
    old = {**rows[1], "source": "simulated", "device_id": "simulator-01"}
    store.insert_measurement(old)
    store.put("alerts", "old", {"source": "simulated", "created_at": old["received_at"]})
    store.initialize()
    assert store.list_rows("measurements") == [rows[0]]
    assert not store.list_rows("alerts")
    store.engine.dispose()
