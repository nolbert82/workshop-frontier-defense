import asyncio
import logging
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import SQLAlchemyError
from backend.app.mqtt import MQTTBridge
from backend.app.schemas import Ack, Telemetry
from backend.app.store import utcnow
from backend.ml.anomaly import Anomaly
from backend.ml.train import train

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.anomaly = Anomaly(settings.model_path)
        self.mqtt = MQTTBridge(settings, self)
        self.lock = asyncio.Lock()
        self.devices = {}
        self.alerts = {}
        self.pending = {}
        self.recent_commands = {}
        self.database = False
        self.training_lock = asyncio.Lock()
        self.vision_at = 0
        self.vision = {"camera": False, "model": False}
        self.actuators = {"buzzer": False, "led": False}
        self.cooldowns = {}
        self.database_failed = False
        self.tasks = []

    async def db(self, method, *args, **kwargs):
        try:
            result = await asyncio.to_thread(getattr(self.store, method), *args, **kwargs)
            self.database = True
            return result
        except SQLAlchemyError:
            self.database = False
            self.database_failed = True
            raise

    async def start(self):
        for attempt in range(10):
            try:
                await self.db("initialize")
                break
            except SQLAlchemyError:
                if attempt == 9:
                    raise
                await asyncio.sleep(2)
        self.alerts = {a["id"]: a for a in await self.db("list_rows", "alerts", 10000) if not a.get("resolved_at")}
        for command in reversed(await self.db("list_rows", "commands", 30)):
            self.track_command(command)
        self.mqtt.start()
        self.tasks = [asyncio.create_task(self.run()), asyncio.create_task(self.mqtt.consume())]

    async def stop(self):
        self.mqtt.stop()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.store.engine.dispose()

    def online(self, device):
        state = self.devices.get(device)
        return bool(state and time.monotonic()-state["seen"] < 5 and not state.get("disconnected"))

    async def ingest(self, payload, allowed_device, allowed_source):
        row = Telemetry.model_validate_json(json.dumps(payload)).model_dump(mode="json")
        if row["device_id"] != allowed_device or row["source"] != allowed_source:
            raise ValueError("Identité ou source ne correspond pas au topic autorisé")
        async with self.lock:
            previous = self.devices.get(row["device_id"])
            if previous:
                latest = previous["latest"]
                if latest["boot_id"] == row["boot_id"] and row["sequence"] <= latest["sequence"]:
                    row["replayed"] = True
            if row["timestamp"] and (datetime.now(timezone.utc)-datetime.fromisoformat(row["timestamp"])).total_seconds() > 5:
                row["replayed"] = True
            row["received_at"] = utcnow()
            inserted = await self.db("insert_measurement", row)
            if inserted and not row["replayed"]:
                decision = await asyncio.to_thread(self.anomaly.evaluate, row)
                row["anomaly"] = decision
                await self.db("update_measurement", row)
                self.devices[row["device_id"]] = {"seen": time.monotonic(), "latest": row, "disconnected": False}
                await self.db("put", "devices", row["device_id"], row)
                prefix = row["device_id"]
                invalid = [k for k, v in row["sensor_status"].items() if v != "ok" or row["sensor_age_ms"][k] > (6000 if k == "dht22" else 2000)]
                await self.condition(prefix+":E002", bool(invalid), "error", "warning", "E002", "Capteur invalide : " + ", ".join(invalid), row["source"])
                await self.condition(prefix+":E009", row["lost_count"] > 0, "error", "warning", "E009", f"{row['lost_count']} mesures perdues depuis le démarrage", row["source"])
                await self.condition(prefix+":anomaly", decision["active"], "anomaly", "critical", None,
                                     "Anomalie environnementale persistante", row["source"])
            return {"device_id": row["device_id"], "boot_id": row["boot_id"], "sequence": row["sequence"], "stored": True, "duplicate": not inserted}

    async def condition(self, key, active, type_, severity, code, message, source):
        existing = next((a for a in self.alerts.values() if a.get("key") == key and not a.get("resolved_at")), None)
        if active and not existing:
            id_ = str(uuid.uuid4())
            data = {"id": id_, "key": key, "event_id": None, "type": type_, "severity": severity, "code": code,
                    "message": message, "source": source, "created_at": utcnow(), "acknowledged_at": None, "resolved_at": None}
            await self.db("put", "alerts", id_, data)
            self.alerts[id_] = data
            if type_ in ("anomaly", "intrusion"):
                await self.signal(type_, source)
        elif not active and existing:
            updated = {**existing, "resolved_at": utcnow()}
            await self.db("put", "alerts", existing["id"], updated)
            self.alerts.pop(existing["id"], None)

    async def signal(self, type_, source):
        now = time.monotonic()
        key = (type_, source)
        device = self.settings.physical_device
        if now-self.cooldowns.get(key, -100) >= 30 and self.online(device):
            self.cooldowns[key] = now
            await self.command({"device_id": device, "type": "buzzer", "value": True, "duration_ms": 3000})

    async def vision_event(self, event):
        async with self.lock:
            existing = await self.db("get", "alerts", event.event_id)
            if existing and (existing["resolved_at"] or event.state == "active"):
                return existing
            if event.state == "resolved" and not existing:
                raise ValueError("Événement à résoudre inconnu")
            data = existing or {"id": event.event_id, "event_id": event.event_id, "type": "intrusion", "severity": "critical", "code": None,
                      "source": event.source, "message": event.message, "created_at": utcnow(), "acknowledged_at": None, "resolved_at": None}
            if data["source"] != event.source:
                raise ValueError("Source différente de celle de l'événement")
            if event.state == "resolved":
                data = {**data, "resolved_at": utcnow()}
            await self.db("put", "alerts", data["id"], data)
            if event.state == "active":
                self.alerts[data["id"]] = data
                if existing is None:
                    await self.signal("intrusion", event.source)
            else:
                self.alerts.pop(data["id"], None)
            return data

    async def command(self, request):
        device = request["device_id"]
        if device != self.settings.physical_device or not self.online(device):
            raise ValueError("Appareil hors ligne : commande indisponible")
        if not self.mqtt.connected:
            raise ValueError("MQTT indisponible")
        latest = self.devices[device]["latest"]
        age = int((time.monotonic()-self.devices[device]["seen"])*1000)
        id_ = str(uuid.uuid4())
        data = {**request, "command_id": id_, "target_boot_id": latest["boot_id"],
                "expires_at_uptime_ms": latest["uptime_ms"]+age+5000, "status": "pending",
                "source": latest["source"], "created_at": utcnow(), "reason": None}
        await self.db("put", "commands", id_, data)
        self.track_command(data)
        self.pending[id_] = {"data": data, "sent": time.monotonic()}
        payload = {k: data[k] for k in ("command_id", "target_boot_id", "expires_at_uptime_ms", "type", "value", "duration_ms")}
        if not self.mqtt.publish(device, "commands", payload):
            # No false acknowledgement; absence of ACK will lead to timeout.
            log.warning("Commande persistée mais publication MQTT indisponible")
        return data

    def track_command(self, data):
        self.recent_commands[data["command_id"]] = data
        while len(self.recent_commands) > 30:
            self.recent_commands.pop(next(iter(self.recent_commands)))

    async def ack(self, ack, device):
        pending = self.pending.get(ack.command_id)
        if not pending:
            return
        command = pending["data"]
        if command["device_id"] != device or command["target_boot_id"] != ack.boot_id:
            raise ValueError("Accusé de commande invalide")
        updated = {**command, "status": ack.result, "reason": ack.reason, "completed_at": utcnow()}
        await self.db("put", "commands", ack.command_id, updated)
        self.track_command(updated)
        self.pending.pop(ack.command_id, None)

    async def mqtt_message(self, topic, data):
        device = self.settings.physical_device
        prefix = f"sentinel/{device}/"
        if not topic.startswith(prefix):
            raise ValueError("Topic refusé")
        suffix = topic[len(prefix):]
        if suffix == "telemetry":
            receipt = await self.ingest(data, device, "physical")
            self.mqtt.publish(device, "receipts", receipt)
        elif suffix == "acks":
            async with self.lock:
                await self.ack(Ack.model_validate(data), device)
        elif suffix == "status" and isinstance(data, dict) and data.get("state") == "offline":
            if device in self.devices:
                self.devices[device]["disconnected"] = True

    def status(self):
        now = time.monotonic()
        devices = {id_: {"online": self.online(id_), "age_seconds": round(now-d["seen"], 1), "latest": d["latest"]} for id_, d in self.devices.items()}
        vision_online = now-self.vision_at < 5
        active = list(self.alerts.values())
        overall = "critical" if any(a["severity"] == "critical" for a in active) else "warning" if active else "normal"
        if not self.database:
            overall = "offline"
        return {"server_time": utcnow(), "overall": overall,
            "devices": devices, "database": self.database, "mqtt": "connected" if self.mqtt.connected else "offline" if self.settings.mqtt_host else "disabled",
            "vision": {**self.vision, "online": vision_online}, "model": bool(self.anomaly.artifact),
            "actuators": {**self.actuators, "system_led": "red" if overall == "critical" else "orange" if overall in ("warning", "offline") else "green"},
            "active_alerts": active, "pending_commands": [p["data"] for p in self.pending.values()],
            "recent_commands": list(reversed(self.recent_commands.values()))}

    async def retrain(self):
        if self.training_lock.locked():
            raise ValueError("Un réentraînement est déjà en cours.")
        async with self.training_lock:
            async with self.lock:
                if not self.online(self.settings.physical_device):
                    raise ValueError("Appareil hors ligne : réentraînement indisponible.")
                now = datetime.now(timezone.utc)
                rows = await self.db("list_rows", "measurements", 1000, 0, self.settings.physical_device,
                                     (now-timedelta(seconds=30)).isoformat())
            artifact = await asyncio.to_thread(train, rows, self.settings.model_path, now)
            async with self.lock:
                self.anomaly.install(artifact)
                for device in self.devices.values():
                    device["latest"]["anomaly"] = {"state": "initializing", "score": None,
                        "threshold": artifact["threshold"], "training_source": "physical"}
                await self.condition("system:E007", False, "error", "warning", "E007", "Modèle disponible", "backend")
            return {k: v for k, v in artifact.items() if k != "model"}

    async def run(self):
        while True:
            started = time.monotonic()
            try:
                await self.db("ping")
                async with self.lock:
                    if self.database_failed:
                        await self.condition("system:E006", True, "error", "critical", "E006", "Base précédemment indisponible ; connexion rétablie", "backend")
                        await self.condition("system:E006", False, "error", "critical", "E006", "Base rétablie", "backend")
                        self.database_failed = False
                    for id_, pending in list(self.pending.items()):
                        data = pending["data"]
                        elapsed = time.monotonic()-pending["sent"]
                        if elapsed >= 5:
                            updated = {**data, "status": "timeout", "reason": "Aucun accusé reçu ; exécution réelle inconnue"}
                            await self.db("put", "commands", id_, updated)
                            self.track_command(updated)
                            self.pending.pop(id_, None)
                            await self.condition(id_+":E008", True, "error", "warning", "E008", updated["reason"], data["source"])
                    expected = []
                    if self.settings.mqtt_host:
                        expected.append(self.settings.physical_device)
                    for device in expected:
                        await self.condition(device+":E001", not self.online(device), "error", "critical", "E001", f"{device} déconnecté — aucune mesure récente", "physical")
                    await self.condition("system:E003", bool(self.settings.mqtt_host) and not self.mqtt.connected, "error", "warning", "E003", "Broker MQTT indisponible", "backend")
                    await self.condition("system:E007", not bool(self.anomaly.artifact), "error", "warning", "E007", "Modèle d'anomalies absent", "backend")
                    await self.condition("system:E005", time.monotonic()-self.vision_at >= 5, "error", "warning", "E005", "Service vision indisponible", "vision")
                    await self.condition("system:E004", time.monotonic()-self.vision_at < 5 and not self.vision["camera"], "error", "warning", "E004", "Webcam indisponible", "vision")
            except Exception:
                log.exception("Cycle dégradé ; nouvelle tentative au prochain cycle")
            await asyncio.sleep(max(.05, 1-(time.monotonic()-started)))
