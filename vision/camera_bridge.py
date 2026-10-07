"""Windows USB acquisition only; YOLO inference stays in the vision container."""
import argparse
import json
import logging
import os
from pathlib import Path
import threading
import time
import cv2
import httpx

log = logging.getLogger("camera")


def select_camera(devices, preferred=None):
    if preferred:
        matches = [d for d in devices if d.name.casefold() == preferred.casefold()]
        if len(matches) == 1:
            return matches[0].index
    excluded = ("integrated", "integrée", "built-in", "built in", "internal", "facetime", "virtual", "obs", "infrared")
    candidates = [d for d in devices if not any(word in d.name.casefold() for word in excluded)]
    if len(candidates) == 1:
        return candidates[0].index
    if len(devices) == 1:
        return devices[0].index
    names = ", ".join(f"{d.index}: {d.name}" for d in devices) or "aucune caméra"
    raise RuntimeError(f"Sélection USB ambiguë ou caméra absente ({names}). Si plusieurs caméras sont branchées, utiliser -Camera INDEX.")


class USBCapture:
    def __init__(self, index, preferred):
        self.index, self.preferred = index, preferred
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.number = 0
        self.thread = threading.Thread(target=self.capture, daemon=True)

    def capture(self):
        camera = None
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        try:
            while not self.stop.is_set():
                if camera is None:
                    try:
                        if self.index is not None:
                            index = self.index
                        else:
                            from cv2_enumerate_cameras import enumerate_cameras
                            index = select_camera(list(enumerate_cameras(backend)), self.preferred)
                        camera = cv2.VideoCapture(index, backend)
                        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        log.info("Caméra sélectionnée : index %s", index)
                    except (RuntimeError, ImportError) as exc:
                        log.warning("%s", exc)
                        self.stop.wait(2)
                        continue
                ok, frame = camera.read()
                if not ok:
                    camera.release()
                    camera = None
                    with self.lock:
                        self.latest = None
                    log.warning("Caméra inaccessible ; nouvelle tentative dans 2 secondes.")
                    self.stop.wait(2)
                    continue
                with self.lock:
                    self.latest = (frame, time.monotonic())
                    self.number += 1
        finally:
            if camera is not None:
                camera.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int)
    parser.add_argument("--config", default="secrets/app.json")
    parser.add_argument("--camera-config", default="vision/camera.json")
    parser.add_argument("--url", default="http://127.0.0.1:8090")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    token = json.loads(Path(args.config).read_text(encoding="utf-8"))["vision_token"]
    configuration = json.loads(Path(args.camera_config).read_text(encoding="utf-8")) if Path(args.camera_config).exists() else {}
    camera = USBCapture(args.camera, configuration.get("name"))
    camera.thread.start()
    previous = -1
    try:
        with httpx.Client(timeout=3, trust_env=False, headers={"Authorization": "Bearer " + token}) as client:
            log.info("Capture USB active ; Ctrl+C arrête la capture. Le modèle tourne dans Docker.")
            while True:
                started = time.monotonic()
                with camera.lock:
                    latest, number = camera.latest, camera.number
                if latest and number != previous and started-latest[1] < 1:
                    previous = number
                    ok, encoded = cv2.imencode(".jpg", cv2.resize(latest[0], (640, 480)), [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ok:
                        try:
                            client.post(args.url+"/frames", content=encoded.tobytes(),
                                        headers={"Content-Type": "image/jpeg"}).raise_for_status()
                        except httpx.HTTPError:
                            log.warning("Conteneur vision inaccessible ; nouvelle tentative dans 2 secondes.")
                            time.sleep(2)
                time.sleep(max(0, .2-(time.monotonic()-started)))
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop.set()
        camera.thread.join(timeout=3)


if __name__ == "__main__":
    main()
