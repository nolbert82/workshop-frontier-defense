"""Windows USB acquisition only; YOLO inference stays in the vision container."""
import argparse
import json
import logging
import multiprocessing
import os
from pathlib import Path
import threading
import time
from queue import Empty, Full
if os.name == "nt":
    # Avoid slow hardware-transform initialization in Media Foundation.
    os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
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


def capture_frames(index, backend, frames, stop):
    """Isolate driver calls: even a blocked Windows driver can be restarted."""
    camera = None
    try:
        camera = cv2.VideoCapture(index, backend)
        if not camera.isOpened():
            return
        # Keep the camera's native format; forcing MJPG fails on some webcams.
        while not stop.is_set():
            ok, frame = camera.read()
            if not ok or frame is None:
                return
            frame = cv2.resize(frame, (640, 480))
            try:
                frames.put_nowait((frame, time.monotonic()))
            except Full:
                pass
            stop.wait(.1)
    except (cv2.error, KeyboardInterrupt):
        return
    finally:
        if camera is not None:
            camera.release()


class USBCapture:
    def __init__(self, index, preferred):
        self.index, self.preferred = index, preferred
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.latest = None
        self.number = 0
        self.thread = threading.Thread(target=self.capture, daemon=True)

    def capture(self):
        context = multiprocessing.get_context("spawn")
        backends = [cv2.CAP_MSMF, cv2.CAP_DSHOW] if os.name == "nt" else [cv2.CAP_ANY]
        attempt = 0
        while not self.stop.is_set():
            backend = backends[attempt % len(backends)]
            attempt += 1
            try:
                from cv2_enumerate_cameras import enumerate_cameras
                devices = list(enumerate_cameras(backend))
                # Enumeration may assign different indices for each Windows driver.
                if self.index is not None:
                    direct = list(enumerate_cameras(cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY))
                    selected = next((d for d in direct if d.index == self.index), None)
                    if selected:
                        match = next((d for d in devices if d.name == selected.name), None)
                        if match is None:
                            raise RuntimeError(f"Webcam {selected.name} indisponible avec ce pilote.")
                        index = match.index
                    else:
                        index = self.index
                else:
                    index = select_camera(devices, self.preferred)
                name = next((d.name for d in devices if d.index == index), str(index))
            except (RuntimeError, ImportError, OSError) as exc:
                log.warning("%s", exc)
                self.stop.wait(2)
                continue
            frames = context.Queue(maxsize=1)
            stopped = context.Event()
            process = context.Process(target=capture_frames, args=(index, backend, frames, stopped), daemon=True)
            process.start()
            last_frame = time.monotonic()
            received = False
            log.info("Ouverture de %s (%s)…", name, "DirectShow" if backend == cv2.CAP_DSHOW else "Media Foundation")
            try:
                while not self.stop.is_set() and process.is_alive():
                    try:
                        latest = frames.get(timeout=.2)
                    except Empty:
                        if time.monotonic()-last_frame > (5 if received else 45):
                            break
                        continue
                    last_frame = time.monotonic()
                    if not received:
                        log.info("Webcam active : %s. Images reçues.", name)
                    received = True
                    with self.lock:
                        self.latest = latest
                        self.number += 1
            finally:
                stopped.set()
                process.join(timeout=1)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
                frames.close()
                frames.cancel_join_thread()
                with self.lock:
                    self.latest = None
            if not self.stop.is_set():
                log.warning("Webcam sans image. Nouvelle tentative automatique avec l'autre pilote. "
                            "Fermer les autres applications caméra et autoriser les applications de bureau "
                            "dans Paramètres Windows > Confidentialité et sécurité > Caméra.")
                self.stop.wait(2)


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
            log.info("Recherche de la webcam USB ; Ctrl+C arrête l'application.")
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
                        except httpx.HTTPError as exc:
                            log.warning("Envoi au service vision impossible : %s. Nouvelle tentative dans 2 secondes.", exc)
                            time.sleep(2)
                time.sleep(max(0, .2-(time.monotonic()-started)))
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop.set()
        camera.thread.join(timeout=5)


if __name__ == "__main__":
    main()
