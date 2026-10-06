"""Configuration locale, sans identifiants de démonstration codés en dur."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    database_url: str = "sqlite:///./data/sentinel.db"
    simulation: bool = True
    secure_cookies: bool = True
    origins: tuple[str, ...] = ("https://localhost",)
    password_hash: str = ""
    vision_token: str = ""
    mqtt_host: str = ""
    mqtt_port: int = 8883
    mqtt_password: str = ""
    mqtt_ca: str = "secrets/ca.crt"
    physical_device: str = "sentinel-x-01"
    vision_url: str = "http://127.0.0.1:8090"
    model_path: str = "backend/ml/model.joblib"
    static_path: str = "frontend/dist"

    @classmethod
    def load(cls):
        path = Path(os.getenv("SENTINEL_CONFIG", str(ROOT / "secrets/app.json")))
        values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for name in cls.__dataclass_fields__:
            env = os.getenv("SENTINEL_" + name.upper())
            if env is not None:
                if name in ("simulation", "secure_cookies"):
                    values[name] = env.lower() == "true"
                elif name == "mqtt_port":
                    values[name] = int(env)
                elif name == "origins":
                    values[name] = env.split(",")
                else:
                    values[name] = env
        settings = cls(**values)
        if not settings.password_hash or not settings.vision_token:
            raise RuntimeError("Configuration absente : exécuter scripts/setup.py.")
        return settings
