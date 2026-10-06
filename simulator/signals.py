"""Séquences déterministes ; aucun capteur ni actionneur physique n'est utilisé."""
import math
import random


def sample(second: int, seed: int = 42, drift: float = 0):
    rng = random.Random(seed * 100000 + second)
    return {
        "temperature": round(24 + .4*math.sin(second/80) + rng.gauss(0, .06) + drift*8, 2),
        "humidity": round(48 + .8*math.sin(second/110) + rng.gauss(0, .15) - drift*5, 2),
        "gas": max(0, min(4095, round(130 + 4*math.sin(second/45) + rng.gauss(0, 1.5) + drift*180))),
        "presence": False,
    }


def telemetry(second, boot_id, scenario="normal", scenario_age=0):
    data = sample(second, drift=min(1.5, scenario_age/45) if scenario == "drift" else 0)
    data.update(device_id="simulator-01", boot_id=boot_id, sequence=second,
        uptime_ms=second*1000, timestamp=None, source="simulated",
        sensor_age_ms={"dht22": (second % 2)*1000, "mq2": 0, "pir": 0},
        sensor_status={"dht22": "ok", "mq2": "ok", "pir": "ok"})
    # DHT22 acquisition every two seconds; preserve both value and age between readings.
    dht = sample(second - second % 2, drift=min(1.5, max(0, scenario_age-second % 2)/45) if scenario == "drift" else 0)
    data.update(temperature=dht["temperature"], humidity=dht["humidity"])
    if scenario == "sensor_error":
        data.update(temperature=None, humidity=None)
        data["sensor_status"]["dht22"] = "error"
    if scenario == "intrusion":
        data["presence"] = True
    return data
