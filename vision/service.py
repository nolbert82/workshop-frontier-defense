"""Un seul propriétaire de la webcam ; dernière image uniquement, pas de vidéo stockée."""
import argparse
from collections import deque
import json
import logging
import os
from pathlib import Path
import statistics
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import uuid
import cv2
import httpx
import numpy as np

log = logging.getLogger("vision")


def camera_index(index, name):
    """Select the configured device by name; never silently switch to another camera."""
    if not name:
        return index
    from cv2_enumerate_cameras import enumerate_cameras
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    matches = [device for device in enumerate_cameras(backend) if device.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise RuntimeError(f"Webcam '{name}' : {len(matches)} périphérique(s) trouvé(s). Utiliser --camera pour sélectionner un index explicitement.")
    return matches[0].index


class PresenceTracker:
    def __init__(self):
        self.positive = 0
        self.last_confirmed = 0
        self.event_id = None

    def update(self, detected, now):
        self.positive = self.positive+1 if detected else 0
        if self.positive >= 3:
            self.last_confirmed = now
            if self.event_id is None:
                self.event_id = str(uuid.uuid4())
                return {"event_id": self.event_id, "state": "active"}
        if self.event_id and now-self.last_confirmed >= 3:
            result = {"event_id": self.event_id, "state": "resolved"}
            self.event_id = None
            return result
        return None


class Vision:
    def __init__(self, args, token):
        self.args, self.token = args, token
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.frame_number = 0
        self.jpeg = None
        self.jpeg_at = 0
        self.camera_ok = False
        self.model_ok = False
        self.latencies = deque(maxlen=300)
        self.events = deque()
        self.tracker = PresenceTracker()
        self.threads = []
        self.stream_id = uuid.uuid4().hex

    def capture(self):
        camera = None
        try:
            while not self.stop.is_set():
                if camera is None:
                    try:
                        selected = self.args.source or camera_index(self.args.camera, self.args.camera_name)
                    except (RuntimeError, ImportError):
                        self.camera_ok = False
                        log.warning("Webcam configurée indisponible", exc_info=True)
                        self.stop.wait(2)
                        continue
                    camera = cv2.VideoCapture(selected, cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY)
                    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    camera.set(cv2.CAP_PROP_FPS, 30)
                    camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, frame = camera.read()
                self.camera_ok = bool(ok)
                if not ok:
                    if camera:
                        camera.release()
                        camera = None
                    with self.lock:
                        self.latest, self.jpeg = None, None
                    self.stop.wait(2)
                    continue
                with self.lock:
                    self.latest = (frame, time.monotonic())
                    self.frame_number += 1
        finally:
            if camera:
                camera.release()

    def analyze(self):
        model = None
        try:
            from ultralytics import YOLO
            if not Path(self.args.model).is_file():
                raise FileNotFoundError("Poids YOLO absents ; aucun téléchargement automatique")
            model = YOLO(self.args.model)
            self.model_ok = True
        except Exception:
            log.exception("Modèle YOLO indisponible")
        previous = -1
        while not self.stop.is_set():
            started = time.monotonic()
            processing_start = time.perf_counter()
            with self.lock:
                latest, number = self.latest, self.frame_number
            if latest and number != previous and started-latest[1] < 1:
                previous = number
                frame = cv2.resize(latest[0], (640, 480))
                detected = False
                try:
                    if model:
                        results = model.predict(frame, classes=[0], conf=.60, imgsz=self.args.imgsz, device="cpu", verbose=False)
                        for result in results:
                            for box in result.boxes:
                                x1, y1, x2, y2 = map(int, box.xyxy[0])
                                cv2.rectangle(frame, (x1, y1), (x2, y2), (115, 222, 173), 2)
                                cv2.putText(frame, "Personne detectee", (x1, max(18, y1-10)), cv2.FONT_HERSHEY_SIMPLEX, .5, (115, 222, 173), 1)
                                detected = True
                    transition = self.tracker.update(detected, time.monotonic())
                    if transition and self.model_ok:
                        transition.update(type="intrusion", source="vision")
                        with self.lock:
                            self.events.append(transition)
                    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    elapsed = (time.perf_counter()-processing_start)*1000
                    if self.model_ok:
                        self.latencies.append(elapsed)
                    if ok:
                        with self.lock:
                            self.jpeg, self.jpeg_at = encoded.tobytes(), latest[1]
                except Exception:
                    self.model_ok = False
                    log.exception("Inférence indisponible")
            self.stop.wait(max(.01, .2-(time.monotonic()-started)))

    def report(self):
        context = None if self.args.url.startswith("http://") else __import__("ssl").create_default_context(cafile=self.args.ca)
        kwargs = {"verify": context} if context else {}
        with httpx.Client(timeout=3, headers={"Authorization": "Bearer " + self.token}, **kwargs) as client:
            while not self.stop.is_set():
                try:
                    latencies = list(self.latencies)
                    with self.lock:
                        fresh = bool(self.jpeg and time.monotonic()-self.jpeg_at < 2)
                    heartbeat = {"camera": self.camera_ok and fresh, "model": self.model_ok,
                        "stream_id": self.stream_id,
                        "median_ms": statistics.median(latencies) if latencies else None,
                        "p95_ms": float(np.percentile(latencies, 95)) if latencies else None}
                    client.post(self.args.url+"/api/v1/vision/heartbeat", json=heartbeat).raise_for_status()
                    with self.lock:
                        event = self.events[0] if self.events else None
                    if event:
                        response = client.post(self.args.url+"/api/v1/alerts", json=event)
                        response.raise_for_status()
                        with self.lock:
                            self.events.popleft()
                except httpx.HTTPError:
                    log.warning("API indisponible ; transition conservée pour réessai")
                self.stop.wait(1)

    def start(self):
        for work in (self.capture, self.analyze, self.report):
            thread = threading.Thread(target=work, daemon=True)
            thread.start()
            self.threads.append(thread)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=os.getenv("VISION_SOURCE"), help="URL du flux webcam ou périphérique /dev/video0")
    parser.add_argument("--camera", type=int, default=None)
    parser.add_argument("--camera-name", default=None)
    parser.add_argument("--camera-config", default="vision/camera.json")
    parser.add_argument("--model", default="vision/model/yolo26n.pt")
    parser.add_argument("--imgsz", type=int, default=320)
    parser.add_argument("--url", default=os.getenv("VISION_BACKEND_URL", "https://localhost"))
    parser.add_argument("--ca", default="secrets/ca.crt")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--config", default="secrets/app.json")
    args = parser.parse_args()
    camera_settings = json.loads(Path(args.camera_config).read_text(encoding="utf-8")) if Path(args.camera_config).exists() else {}
    if args.camera is None:
        args.camera = camera_settings.get("index", 0)
        args.camera_name = args.camera_name or camera_settings.get("name")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler()])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = json.loads(Path(args.config).read_text(encoding="utf-8"))["vision_token"]
    vision = Vision(args, token)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token):
                self.send_error(401)
                return
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"alive":true}')
                return
            if self.path != "/stream":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while not vision.stop.is_set():
                    with vision.lock:
                        jpeg, captured = vision.jpeg, vision.jpeg_at
                    if jpeg and time.monotonic()-captured < 2:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode()+b"\r\n\r\n"+jpeg+b"\r\n")
                        self.wfile.flush()
                    elif time.monotonic()-captured >= 2:
                        break
                    vision.stop.wait(.2)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    vision.start()
    print(f"Vision {args.camera_name or 'USB index '+str(args.camera)} : {args.bind}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        vision.stop.set()
        server.server_close()


if __name__ == "__main__":
    main()
