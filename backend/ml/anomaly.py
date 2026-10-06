from collections import deque
from pathlib import Path
import joblib
import numpy as np


FEATURES = ["temperature", "humidity", "gas", "delta_temperature", "delta_gas", "mean_gas", "std_gas"]


def features(rows):
    gas = np.array([r["gas"] for r in rows], dtype=float)
    return [rows[-1]["temperature"], rows[-1]["humidity"], gas[-1],
            rows[-1]["temperature"]-rows[0]["temperature"], gas[-1]-gas[0], gas.mean(), gas.std()]


class Anomaly:
    def __init__(self, path):
        try:
            self.artifact = joblib.load(path) if Path(path).exists() else None
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Modèle illisible : analyse indisponible")
            self.artifact = None
        self.windows = {}
        self.states = {}

    def evaluate(self, row):
        device = row["device_id"]
        window = self.windows.setdefault(device, deque(maxlen=30))
        state = self.states.setdefault(device, {"state": "initializing", "score": None, "positive": 0, "negative": 0, "active": False, "last_sequence": -2, "boot_id": row["boot_id"]})
        if state["boot_id"] != row["boot_id"]:
            window.clear()
            state.update(boot_id=row["boot_id"], last_sequence=-2, positive=0, negative=0)
        if window and (row["uptime_ms"]-window[-1]["uptime_ms"] > 2000):
            window.clear()
            state.update(positive=0, negative=0)
        valid = all(row[k] is not None for k in ("temperature", "humidity", "gas")) and all(row["sensor_status"][k] == "ok" for k in ("dht22", "mq2")) and row["sensor_age_ms"]["dht22"] <= 6000 and row["sensor_age_ms"]["mq2"] <= 2000
        if not valid:
            window.clear()
            state.update(state="unavailable", score=None, positive=0, negative=0)
            return dict(state)
        window.append(row)
        if not self.artifact:
            state.update(state="unavailable", score=None)
        elif len(window) < 30 or window[-1]["uptime_ms"]-window[0]["uptime_ms"] < 29000:
            state.update(state="initializing", score=None)
        elif row["sequence"]-state["last_sequence"] >= 2:
            score = float(-self.artifact["model"].score_samples([features(list(window))])[0])
            unusual = score > self.artifact["threshold"]
            state["positive"] = state["positive"]+1 if unusual else 0
            state["negative"] = 0 if unusual else state["negative"]+1
            if state["positive"] >= 3:
                state["active"] = True
            if state["negative"] >= 10:
                state["active"] = False
            state.update(score=score, state="critical" if state["active"] else "warning" if unusual else "normal", last_sequence=row["sequence"])
        state["threshold"] = self.artifact["threshold"] if self.artifact else None
        state["training_source"] = self.artifact["training_source"] if self.artifact else None
        return dict(state)
