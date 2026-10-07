from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Ages(StrictModel):
    dht22: int = Field(ge=0, le=86400000)
    mq2: int = Field(ge=0, le=86400000)
    pir: int = Field(ge=0, le=86400000)


class SensorStates(StrictModel):
    dht22: Literal["ok", "error", "stale", "warming_up"]
    mq2: Literal["ok", "error", "stale", "warming_up"]
    pir: Literal["ok", "error", "stale", "warming_up"]


class Telemetry(StrictModel):
    device_id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    boot_id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,64}$")
    sequence: int = Field(ge=0, le=2**63-1)
    uptime_ms: int = Field(ge=0, le=2**63-1)
    timestamp: datetime | None = None
    temperature: float | None = Field(default=None, ge=-40, le=80)
    humidity: float | None = Field(default=None, ge=0, le=100)
    gas: int | None = Field(default=None, ge=0, le=4095)
    presence: bool | None = None
    sensor_age_ms: Ages
    sensor_status: SensorStates
    source: Literal["physical"]
    replayed: bool = False
    lost_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def valid_readings(self):
        if self.timestamp is not None and self.timestamp.tzinfo is None:
            raise ValueError("timestamp doit inclure son fuseau UTC")
        for sensor, fields in {"dht22": ("temperature", "humidity"), "mq2": ("gas",), "pir": ("presence",)}.items():
            if getattr(self.sensor_status, sensor) != "ok":
                for field in fields:
                    if getattr(self, field) is not None:
                        raise ValueError(f"{field} doit être null lorsque {sensor} est invalide")
            elif any(getattr(self, field) is None for field in fields):
                raise ValueError(f"{sensor} annoncé ok doit fournir toutes ses valeurs")
        return self


class CommandRequest(StrictModel):
    device_id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    type: Literal["buzzer", "led"]
    value: bool
    duration_ms: int = Field(default=3000, ge=100, le=10000)


class Ack(StrictModel):
    command_id: str = Field(max_length=64)
    boot_id: str = Field(max_length=64)
    result: Literal["executed", "rejected"]
    reason: str | None = Field(default=None, max_length=200)


class VisionEvent(StrictModel):
    event_id: str = Field(pattern=r"^[a-zA-Z0-9-]{1,80}$")
    type: Literal["intrusion"] = "intrusion"
    state: Literal["active", "resolved"]
    source: Literal["vision"] = "vision"
    message: str = Field(default="Personne détectée dans la zone surveillée", max_length=300)


class Heartbeat(StrictModel):
    camera: bool
    model: bool
    median_ms: float | None = Field(default=None, ge=0)
    p95_ms: float | None = Field(default=None, ge=0)
    stream_id: str | None = Field(default=None, max_length=64)


class Login(StrictModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=256)
