import asyncio
import json
import logging
import ssl
from paho.mqtt import client as mqtt

log = logging.getLogger(__name__)


class MQTTBridge:
    def __init__(self, settings, runtime):
        self.settings, self.runtime = settings, runtime
        self.connected = False
        self.client = None
        self.loop = None
        self.queue = asyncio.Queue(maxsize=120)

    def start(self):
        if not self.settings.mqtt_host:
            return
        self.loop = asyncio.get_running_loop()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sentinel-backend")
        client.username_pw_set("backend", self.settings.mqtt_password)
        client.tls_set(ca_certs=self.settings.mqtt_ca, cert_reqs=ssl.CERT_REQUIRED)
        client.reconnect_delay_set(1, 10)
        client.max_queued_messages_set(120)
        client.on_connect = self.on_connect
        client.on_disconnect = lambda *_: self.loop.call_soon_threadsafe(setattr, self, "connected", False)
        client.on_message = self.on_message
        self.client = client
        client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, 15)
        client.loop_start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.loop.call_soon_threadsafe(setattr, self, "connected", not reason_code.is_failure)
        if not reason_code.is_failure:
            prefix = f"sentinel/{self.settings.physical_device}/"
            client.subscribe([(prefix + name, 1) for name in ("telemetry", "status", "acks")])

    def enqueue(self, topic, data):
        try:
            self.queue.put_nowait((topic, data))
        except asyncio.QueueFull:
            log.warning("File MQTT pleine : pas de reçu, le boîtier devra réessayer")

    def on_message(self, client, userdata, msg):
        if len(msg.payload) > 8192:
            log.warning("Payload MQTT trop grand")
            return
        try:
            data = json.loads(msg.payload)
            # A retained measurement or command acknowledgement must not become live state.
            if msg.retain and msg.topic.endswith(("telemetry", "acks")):
                return
            self.loop.call_soon_threadsafe(self.enqueue, msg.topic, data)
        except (ValueError, UnicodeError):
            log.warning("JSON MQTT invalide")

    async def consume(self):
        while True:
            topic, data = await self.queue.get()
            try:
                await self.runtime.mqtt_message(topic, data)
            except Exception:
                log.exception("Message MQTT refusé ou stockage indisponible ; aucun reçu envoyé")
            finally:
                self.queue.task_done()

    def publish(self, device, suffix, data):
        if not self.client or not self.connected:
            return False
        result = self.client.publish(f"sentinel/{device}/{suffix}", json.dumps(data), qos=1, retain=False)
        return result.rc == mqtt.MQTT_ERR_SUCCESS

    def stop(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
