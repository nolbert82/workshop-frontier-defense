"""Calibration manuelle sur les 30 dernières secondes de mesures physiques."""
from datetime import datetime, timezone
from pathlib import Path
import os
import tempfile
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

FEATURES = ["temperature", "humidity", "gas"]


def valid(row):
    return (row.get("source") == "physical" and not row.get("replayed", False)
            and all(row.get(k) is not None for k in FEATURES)
            and all(row["sensor_status"][k] == "ok" for k in ("dht22", "mq2"))
            and row["sensor_age_ms"]["dht22"] <= 6000
            and row["sensor_age_ms"]["mq2"] <= 2000)


def features(row):
    return [row[k] for k in FEATURES]


def train(rows, output, now=None):
    now = now or datetime.now(timezone.utc)
    rows = sorted((r for r in rows if 0 <= (now-datetime.fromisoformat(r["received_at"])).total_seconds() <= 30),
                  key=lambda r: r["uptime_ms"])
    if (len(rows) < 30 or not all(valid(r) for r in rows)
            or len({(r["device_id"], r["boot_id"]) for r in rows}) != 1
            or rows[-1]["uptime_ms"]-rows[0]["uptime_ms"] < 29000
            or (now-datetime.fromisoformat(rows[-1]["received_at"])).total_seconds() > 2
            or any(not 0 < b["uptime_ms"]-a["uptime_ms"] <= 2000 or b["sequence"] != a["sequence"]+1
                   for a, b in zip(rows, rows[1:]))):
        raise ValueError("Collectez 30 secondes continues de mesures physiques valides avant de réentraîner.")
    observations = [features(r) for r in rows]
    model = IsolationForest(n_estimators=100, random_state=42, n_jobs=1).fit(observations)
    artifact = {"model": model, "version": "physical-30s-v1", "training_source": "physical",
                "device_id": rows[-1]["device_id"], "features": FEATURES,
                "threshold": float(np.quantile(-model.score_samples(observations), .995)),
                "trained_at": now.isoformat(), "samples": len(rows), "window_seconds": 30}
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".joblib")
    os.close(fd)
    try:
        joblib.dump(artifact, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return artifact
