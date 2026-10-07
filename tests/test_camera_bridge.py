import hashlib
import io
from http.server import ThreadingHTTPServer
import threading
import time
from types import SimpleNamespace
import cv2
import httpx
import numpy as np
import pytest
from vision.camera_bridge import select_camera, capture_frames, USBCapture
from vision import camera_bridge
from vision.service import Vision, handler_for
from vision import weights


@pytest.fixture
def bridge():
    vision = Vision(SimpleNamespace(source="bridge"), "test-token")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(vision, "test-token"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False) as client:
        yield client, vision
    vision.stop.set()
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def jpeg(width=640, height=480):
    ok, encoded = cv2.imencode(".jpg", np.zeros((height, width, 3), dtype=np.uint8))
    assert ok
    return encoded.tobytes()


def test_usb_frames_require_secret_and_update_only_latest(bridge):
    client, vision = bridge
    content = jpeg()
    assert client.post("/frames", content=content, headers={"Content-Type": "image/jpeg"}).status_code == 401
    assert vision.latest is None
    headers = {"Authorization": "Bearer test-token", "Content-Type": "image/jpeg"}
    for _ in range(3):
        assert client.post("/frames", content=content, headers=headers).status_code == 204
    assert vision.frame_number == 3 and vision.camera_ok
    assert vision.latest[0].shape == (480, 640, 3)
    assert time.monotonic()-vision.latest[1] < 1
    assert client.get("/stream").status_code == 401
    assert client.get("/health", headers=headers).status_code == 200
    assert client.get("/health", headers=headers).json() == {"alive": True, "camera": True, "model": False}


@pytest.mark.parametrize("content,content_type,status", [
    (b"invalid", "image/jpeg", 400),
    (b"\xff\xd8invalid", "image/jpeg", 400),
    (b"invalid", "application/json", 415),
    (b"x"*(1024*1024+1), "image/jpeg", 413),
    (b"", "image/jpeg", 413),
], ids=["not-jpeg", "corrupt-jpeg", "wrong-type", "too-large", "empty"])
def test_bridge_rejects_invalid_upload(bridge, content, content_type, status):
    client, vision = bridge
    response = client.post("/frames", content=content, headers={
        "Authorization": "Bearer test-token", "Content-Type": content_type})
    assert response.status_code == status
    assert vision.latest is None


def test_bridge_rejects_wrong_resolution_and_other_sources(bridge):
    client, vision = bridge
    headers = {"Authorization": "Bearer test-token", "Content-Type": "image/jpeg"}
    assert client.post("/frames", content=jpeg(320, 240), headers=headers).status_code == 400
    vision.args.source = "/dev/video0"
    assert client.post("/frames", content=jpeg(), headers=headers).status_code == 404
    assert vision.latest is None


def test_bridge_marks_unplugged_camera_unavailable():
    vision = Vision(SimpleNamespace(source="bridge"), "test-token")
    vision.latest = (np.zeros((480, 640, 3)), time.monotonic()-3)
    vision.camera_ok = True
    class OneCycle:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, seconds): self.stopped = True
    vision.stop = OneCycle()
    vision.capture()
    assert not vision.camera_ok


def test_camera_selection_prefers_usb_and_handles_different_machine():
    integrated = SimpleNamespace(index=0, name="Integrated Camera")
    external = SimpleNamespace(index=2, name="USB Camera")
    assert select_camera([integrated, external], "UGREEN Camera") == 2
    assert select_camera([external]) == 2
    assert select_camera([integrated]) == 0
    other = SimpleNamespace(index=3, name="UGREEN Camera")
    assert select_camera([integrated, external, other], "UGREEN Camera") == 3
    with pytest.raises(RuntimeError, match="-Camera"):
        select_camera([external, other])
    with pytest.raises(RuntimeError): select_camera([])


def test_capture_keeps_native_format_and_releases_device(monkeypatch):
    released = []
    class Device:
        def isOpened(self): return True
        def read(self): return True, np.zeros((720, 1280, 3), dtype=np.uint8)
        def release(self): released.append(True)
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def wait(self, seconds): self.stopped = True
    frames = []
    monkeypatch.setattr(cv2, "VideoCapture", lambda index, backend: Device())
    capture_frames(0, cv2.CAP_MSMF, SimpleNamespace(put_nowait=frames.append), Stop())
    assert frames[0][0].shape == (480, 640, 3)
    assert released == [True]


def test_capture_releases_device_on_driver_error(monkeypatch):
    released = []
    class Device:
        def isOpened(self): return True
        def read(self): raise cv2.error("driver failed")
        def release(self): released.append(True)
    monkeypatch.setattr(cv2, "VideoCapture", lambda index, backend: Device())
    capture_frames(0, cv2.CAP_MSMF, None, threading.Event())
    assert released == [True]


def test_blocked_driver_is_terminated_and_capture_can_stop(monkeypatch):
    from queue import Empty
    capture = USBCapture(None, "USB Camera")
    stopped = threading.Event()
    calls = []
    class Frames:
        def get(self, timeout): raise Empty
        def close(self): calls.append("queue closed")
        def cancel_join_thread(self): pass
    class Process:
        alive = True
        def start(self): pass
        def is_alive(self): return self.alive
        def join(self, timeout): pass
        def terminate(self):
            calls.append("terminated")
            self.alive = False
            capture.stop.set()
    context = SimpleNamespace(Queue=lambda **kwargs: Frames(), Event=lambda: stopped,
                              Process=lambda **kwargs: Process())
    monkeypatch.setattr(camera_bridge.multiprocessing, "get_context", lambda method: context)
    import cv2_enumerate_cameras
    monkeypatch.setattr(cv2_enumerate_cameras, "enumerate_cameras",
                        lambda backend: [SimpleNamespace(index=0, name="USB Camera")])
    times = iter([0, 46])
    monkeypatch.setattr(camera_bridge.time, "monotonic", lambda: next(times))
    capture.capture()
    assert calls == ["terminated", "queue closed"]
    assert stopped.is_set() and capture.latest is None


def test_pretrained_weights_download_verified_and_cached(tmp_path, monkeypatch):
    content = b"test-checkpoint"
    monkeypatch.setattr(weights, "SHA256", hashlib.sha256(content).hexdigest())
    calls = []
    def fetch(url, timeout):
        calls.append(url)
        return io.BytesIO(content)
    monkeypatch.setattr(weights.urllib.request, "urlopen", fetch)
    path = tmp_path/"models"/"yolo26n.pt"
    weights.download(path)
    weights.download(path)
    assert path.read_bytes() == content
    assert calls == [weights.URL]


def test_wrong_weights_do_not_replace_existing_file(tmp_path, monkeypatch):
    path = tmp_path/"yolo26n.pt"
    path.write_bytes(b"previous-checkpoint")
    monkeypatch.setattr(weights.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="Empreinte"): weights.download(path)
    assert path.read_bytes() == b"previous-checkpoint"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_download_cleans_partial_file(tmp_path, monkeypatch):
    def fail(*args, **kwargs): raise OSError("network unavailable")
    monkeypatch.setattr(weights.urllib.request, "urlopen", fail)
    with pytest.raises(OSError): weights.download(tmp_path/"yolo26n.pt")
    assert not list(tmp_path.iterdir())
