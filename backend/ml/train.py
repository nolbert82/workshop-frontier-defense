"""Entraînement HORS LIGNE sur séquences synthétiques disjointes."""
import json
import argparse
from collections import deque
from pathlib import Path
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from simulator.signals import sample
from backend.ml.anomaly import FEATURES, features


def windows(seed, count=1200, drift=False):
    rows = [sample(i, seed, min(1.5, max(0, i-100)/100) if drift else 0) for i in range(count)]
    return [features(rows[i-29:i+1]) for i in range(29, count, 2)]


def recorded_windows(paths, expected_source=None):
    observations = []
    for path in paths:
        window = deque(maxlen=30)
        last_key = None
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            row = item.get("data", item)
            if item.get("table", "measurements") != "measurements":
                continue
            if expected_source and row.get("source") != expected_source:
                raise ValueError("La provenance des mesures ne correspond pas au manifeste")
            key = (row["device_id"], row["boot_id"])
            valid = not row.get("replayed", False) and all(row.get(k) is not None for k in ("temperature", "humidity", "gas")) and all(row["sensor_status"][k] == "ok" for k in ("dht22", "mq2")) and row["sensor_age_ms"]["dht22"] <= 6000 and row["sensor_age_ms"]["mq2"] <= 2000
            if not valid or key != last_key or (window and not 0 < row["uptime_ms"]-window[-1]["uptime_ms"] <= 2000):
                window.clear()
            last_key = key
            if not valid:
                continue
            window.append(row)
            if len(window) == 30 and row["uptime_ms"]-window[0]["uptime_ms"] >= 29000 and row["sequence"] % 2 == 0:
                observations.append(features(list(window)))
    if len(observations) < 20:
        raise ValueError("Séquence insuffisante : au moins 20 fenêtres valides ordonnées sont nécessaires")
    return observations


def train(output="backend/ml/model.joblib", manifest=None):
    source = "simulated"
    splits = {"train": 10, "validation": 20, "test_normal": 30, "test_drift": 40}
    datasets = None
    if manifest:
        specification = json.loads(Path(manifest).read_text(encoding="utf-8"))
        source = specification["source"]
        if source not in ("physical", "simulated"):
            raise ValueError("Source invalide")
        splits = specification["sequences"]
        all_paths = [str(Path(p).resolve()) for name in ("train", "validation", "test_normal", "test_drift") for p in splits[name]]
        if len(set(all_paths)) != len(all_paths):
            raise ValueError("Un fichier ne peut pas appartenir à plusieurs jeux")
        datasets = {name: recorded_windows(paths, source) for name, paths in splits.items()}
    model = IsolationForest(n_estimators=100, random_state=42, n_jobs=1).fit(datasets["train"] if datasets else windows(10))
    validation = -model.score_samples(datasets["validation"] if datasets else windows(20))
    threshold = float(np.quantile(validation, .995))
    normal = -model.score_samples(datasets["test_normal"] if datasets else windows(30))
    abnormal = -model.score_samples(datasets["test_drift"] if datasets else windows(40, drift=True))
    metadata = {"version": "recorded-v1" if datasets else "synthetic-v1", "training_source": source, "features": FEATURES,
        "threshold": threshold, "n_estimators": 100, "seed": 42,
        "sequences": splits,
        "normal_observations_over_threshold": int((normal > threshold).sum()),
        "normal_observations": len(normal), "drift_observations_over_threshold": int((abnormal > threshold).sum()),
        "drift_observations": len(abnormal),
        "limitations": "Évaluation par observations, pas par épisodes. Ce score n'est pas une probabilité. " + ("Données synthétiques uniquement ; recalibrer sur collecte physique." if source == "simulated" else "Vérifier la représentativité des séquences et les fausses alertes par épisode.")}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, **metadata}, output)
    Path(output).with_suffix(".json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="backend/ml/model.joblib")
    parser.add_argument("--manifest", help="Manifest des quatre jeux temporels distincts JSONL")
    arguments = parser.parse_args()
    train(arguments.output, arguments.manifest)
