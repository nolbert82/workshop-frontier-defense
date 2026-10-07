import asyncio
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.schemas import Telemetry, Ack
from backend.app.security import hash_password
from backend.app.store import Store
from backend.app.runtime import Runtime
from backend.ml.anomaly import Anomaly
def telemetry(sequence, boot):
    return {"device_id": "sentinel-x-01", "boot_id": boot, "sequence": sequence,
        "uptime_ms": sequence*1000, "temperature": 24.0, "humidity": 48.0, "gas": 130,
        "presence": False, "timestamp": None, "source": "physical", "replayed": False,
        "sensor_age_ms": {"dht22": 0, "mq2": 0, "pir": 0},
        "sensor_status": {"dht22": "ok", "mq2": "ok", "pir": "ok"}}
from vision.service import PresenceTracker


def test_camera_selected_by_name_without_fallback(monkeypatch):
    from types import SimpleNamespace
    import sys
    cv2_enumerate_cameras = SimpleNamespace(enumerate_cameras=lambda backend: [])
    monkeypatch.setitem(sys.modules, "cv2_enumerate_cameras", cv2_enumerate_cameras)
    from vision.service import camera_index
    monkeypatch.setattr(cv2_enumerate_cameras, "enumerate_cameras", lambda backend: [
        SimpleNamespace(index=2, name="UGREEN Camera"), SimpleNamespace(index=0, name="Integrated Camera")])
    assert camera_index(0, "ugreen camera") == 2
    with pytest.raises(RuntimeError):
        camera_index(0, "Disconnected Camera")
    assert camera_index(1, None) == 1


def test_vision_heartbeat_identifies_stream_restart(client):
    service = {"Authorization": "Bearer test-vision-secret"}
    for stream_id in ("first-stream", "restarted-stream"):
        response = client.post("/api/v1/vision/heartbeat", headers=service, json={
            "camera": True, "model": True, "stream_id": stream_id})
        assert response.status_code == 200
        login(client)
        assert client.get("/api/v1/status").json()["vision"]["stream_id"] == stream_id


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path/'test.db'}", password_hash=hash_password("test-password"),
                    vision_token="test-vision-secret", secure_cookies=True, origins=("https://testserver",), static_path="absent")


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        yield client


def login(client):
    result = client.post("/api/v1/login", headers={"Origin":"https://testserver"}, json={"username":"operateur","password":"test-password"})
    assert result.status_code == 200
    cookie = result.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    return {"Origin":"https://testserver", "X-CSRF-Token":result.json()["csrf_token"]}


def test_authentication_and_csrf(client):
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/api/v1/video").status_code == 401
    headers = login(client)
    assert client.get("/api/v1/status").status_code == 200
    assert client.post("/api/v1/logout", json={}).status_code == 403
    assert client.post("/api/v1/logout", headers={**headers,"Origin":"https://evil.example"}, json={}).status_code == 403
    assert client.post("/api/v1/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/status").status_code == 401


def test_login_rate_limit(client):
    for _ in range(5):
        assert client.post("/api/v1/login", headers={"Origin":"https://testserver"}, json={"username":"operateur","password":"wrong"}).status_code == 401
    assert client.post("/api/v1/login", headers={"Origin":"https://testserver"}, json={"username":"operateur","password":"wrong"}).status_code == 429


def test_service_events_idempotency_and_ack(client):
    event={"event_id":"person-1", "state":"active", "source":"vision"}
    assert client.post("/api/v1/alerts", json=event).status_code == 401
    service={"Authorization":"Bearer test-vision-secret"}
    first=client.post("/api/v1/alerts", headers=service, json=event)
    assert first.status_code == 200
    assert client.post("/api/v1/alerts", headers=service, json=event).json()==first.json()
    headers=login(client)
    ack=client.post("/api/v1/alerts/person-1/ack", headers=headers)
    assert ack.json()["acknowledged_at"] and not ack.json()["resolved_at"]
    assert client.post("/api/v1/alerts", headers=service, json={**event,"state":"resolved"}).json()["resolved_at"]
    rows=client.get("/api/v1/alerts").json()["items"]
    assert len([r for r in rows if r["id"]=="person-1"])==1
    client.cookies.clear()
    assert client.post("/api/v1/commands", headers=service, json={"device_id":"sentinel-x-01","type":"buzzer","value":True}).status_code==401


def test_websocket_security_and_snapshot(client):
    login(client)
    with client.websocket_connect("wss://testserver/api/v1/ws", headers={"Origin":"https://testserver"}) as socket:
        assert socket.receive_json()["type"] == "snapshot"
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("wss://testserver/api/v1/ws", headers={"Origin":"https://evil.example"}):
            pass


def test_offline_and_validation(client):
    headers=login(client)
    payload={"device_id":"sentinel-x-01","type":"buzzer","value":True}
    assert client.post("/api/v1/commands", headers=headers, json=payload).status_code==409
    assert client.post("/api/v1/commands", headers=headers, json={**payload,"value":"true"}).status_code==422
    assert client.post("/api/v1/simulation", headers=headers, json={"scenario":"normal"}).status_code==404


def test_deduplication_replay_identity_and_restart(settings):
    async def run():
        store=Store(settings.database_url);store.initialize();runtime=Runtime(settings,store)
        row=telemetry(40,"boot-1")
        first=await runtime.ingest(row,"sentinel-x-01","physical")
        duplicate=await runtime.ingest(row,"sentinel-x-01","physical")
        assert first["stored"] and duplicate["duplicate"]
        assert len(store.list_rows("measurements"))==1
        seen=runtime.devices["sentinel-x-01"]["seen"]
        await runtime.ingest(telemetry(20,"boot-1"),"sentinel-x-01","physical")
        assert runtime.devices["sentinel-x-01"]["latest"]["sequence"]==40
        assert runtime.devices["sentinel-x-01"]["seen"]==seen
        assert store.list_rows("measurements")[0]["replayed"]
        with pytest.raises(ValueError):
            await runtime.ingest(row,"other-device","physical")
        store.engine.dispose()
        reopened=Store(settings.database_url)
        assert len(reopened.list_rows("measurements"))==2
        reopened.engine.dispose()
    asyncio.run(run())


def test_mqtt_iso_timestamp_parsed_strictly(settings):
    async def run():
        store=Store(settings.database_url);store.initialize();runtime=Runtime(settings,store)
        from backend.app.store import utcnow
        row={**telemetry(1,"known-time"),"timestamp":utcnow()}
        assert (await runtime.ingest(row,"sentinel-x-01","physical"))["stored"]
        assert runtime.devices["sentinel-x-01"]["latest"]["timestamp"]
        store.engine.dispose()
    asyncio.run(run())


def test_storage_failure_never_receipted(settings):
    from sqlalchemy.exc import OperationalError
    async def run():
        store=Store(settings.database_url);store.initialize();runtime=Runtime(settings,store)
        def fail(*args): raise OperationalError("insert",{},Exception("offline"))
        store.insert_measurement=fail
        with pytest.raises(OperationalError): await runtime.ingest(telemetry(1,"boot"),"sentinel-x-01","physical")
        assert not runtime.database and not runtime.devices
        store.engine.dispose()
    asyncio.run(run())


def test_command_ack_wrong_boot_duplicate_and_timeout(settings):
    async def run():
        store=Store(settings.database_url);store.initialize();runtime=Runtime(settings,store)
        runtime.mqtt.connected = True
        runtime.mqtt.publish = lambda *args: True
        await runtime.ingest(telemetry(40,"boot"),"sentinel-x-01","physical")
        cmd=await runtime.command({"device_id":"sentinel-x-01","type":"buzzer","value":True,"duration_ms":3000})
        assert cmd["status"]=="pending"
        with pytest.raises(ValueError): await runtime.ack(Ack(command_id=cmd["command_id"],boot_id="other",result="executed"),"sentinel-x-01")
        ack=Ack(command_id=cmd["command_id"],boot_id="boot",result="executed")
        await runtime.ack(ack,"sentinel-x-01");await runtime.ack(ack,"sentinel-x-01")
        assert store.get("commands",cmd["command_id"])["status"]=="executed"
        assert runtime.status()["recent_commands"][0]["status"]=="executed"
        pending=await runtime.command({"device_id":"sentinel-x-01","type":"led","value":True,"duration_ms":3000})
        runtime.pending[pending["command_id"]]["sent"]-=6
        task=asyncio.create_task(runtime.run())
        await asyncio.sleep(.3)
        task.cancel();await asyncio.gather(task,return_exceptions=True)
        assert store.get("commands",pending["command_id"])["status"]=="timeout"
        store.engine.dispose()
    asyncio.run(run())


def test_presence_confirmation_and_resolution():
    tracker=PresenceTracker()
    assert not tracker.update(True,1)
    assert not tracker.update(True,1.2)
    event=tracker.update(True,1.4)
    assert event["state"]=="active"
    assert not tracker.update(False,2)
    assert not tracker.update(False,4.3)
    resolved=tracker.update(False,4.5)
    assert resolved["event_id"]==event["event_id"] and resolved["state"]=="resolved"


def test_invalid_sensor_null_and_bounds():
    row=telemetry(1,"boot")
    with pytest.raises(ValueError): Telemetry.model_validate({**row,"temperature":100})
    row["sensor_status"]["dht22"]="error"
    with pytest.raises(ValueError): Telemetry.model_validate(row)
    Telemetry.model_validate({**row,"temperature":None,"humidity":None})
