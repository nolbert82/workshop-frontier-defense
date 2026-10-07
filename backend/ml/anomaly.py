from pathlib import Path
import joblib


from backend.ml.train import FEATURES, features, valid


class Anomaly:
    def __init__(self, path):
        try:
            self.artifact = joblib.load(path) if Path(path).exists() else None
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Modèle illisible : analyse indisponible")
            self.artifact = None
        if self.artifact and (self.artifact.get("training_source") != "physical" or self.artifact.get("features") != FEATURES):
            self.artifact = None
        self.states = {}

    def install(self, artifact):
        self.artifact = artifact
        for state in self.states.values():
            state.update(state="initializing", score=None, positive=0, negative=0, last_sequence=-2)

    def evaluate(self, row):
        device = row["device_id"]
        state = self.states.setdefault(device, {"state": "initializing", "score": None, "positive": 0, "negative": 0, "active": False, "last_sequence": -2, "boot_id": row["boot_id"], "uptime_ms": 0})
        if state["boot_id"] != row["boot_id"]:
            state.update(boot_id=row["boot_id"], last_sequence=-2, positive=0, negative=0)
        if row["uptime_ms"]-state["uptime_ms"] > 2000:
            state.update(positive=0, negative=0)
        state["uptime_ms"] = row["uptime_ms"]
        if not valid(row):
            state.update(state="unavailable", score=None, positive=0, negative=0)
            return dict(state)
        if not self.artifact or self.artifact["device_id"] != device:
            state.update(state="unavailable", score=None)
        elif row["sequence"]-state["last_sequence"] >= 2:
            score = float(-self.artifact["model"].score_samples([features(row)])[0])
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
