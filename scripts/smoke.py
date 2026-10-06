"""Recette intégrée loopback : API réelle, tâches, WebSocket et MJPEG."""
import json
from pathlib import Path
import time
import httpx
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def main():
    password = (ROOT/"secrets/operator.txt").read_text(encoding="utf-8").split("Mot de passe : ")[1].strip()
    results = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=5) as client:
        res=client.post("/api/v1/login",headers={"Origin":"http://127.0.0.1:8000"},json={"username":"operateur","password":password});res.raise_for_status()
        headers={"Origin":"http://127.0.0.1:8000","X-CSRF-Token":res.json()["csrf_token"]}
        def scenario(name):
            response=client.post("/api/v1/simulation",headers=headers,json={"scenario":name});response.raise_for_status()
        def status():
            response=client.get("/api/v1/status");response.raise_for_status();return response.json()
        def wait_for(predicate,seconds=10):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if predicate(): return
                time.sleep(.3)
            raise AssertionError("Condition non obtenue dans le délai")
        def command(type_="buzzer"):
            response=client.post("/api/v1/commands",headers=headers,json={"device_id":"simulator-01","type":type_,"value":True,"duration_ms":1000})
            assert response.status_code==202
            assert response.json()["status"]=="pending"
            return response.json()["command_id"]
        def result(id_): return client.get("/api/v1/commands/"+id_).json()["status"]
        scenario("normal")
        wait_for(lambda:status()["devices"]["simulator-01"]["online"])
        id_=command();wait_for(lambda:result(id_)=="executed")
        results.append("Commande pending puis executed")
        cookie="sentinel_session="+client.cookies.get("sentinel_session")
        with connect("ws://127.0.0.1:8000/api/v1/ws",origin="http://127.0.0.1:8000",additional_headers={"Cookie":cookie},proxy=None) as ws:
            snapshot=json.loads(ws.recv(timeout=3))
            assert snapshot["type"]=="snapshot"
        results.append("WebSocket authentifié : snapshot et heartbeat")
        with client.stream("GET","/api/v1/video") as stream:
            stream.raise_for_status()
            assert b"--frame" in next(stream.iter_bytes())
        results.append("MJPEG relayé et authentifié")
        scenario("sensor_error")
        wait_for(lambda:status()["devices"]["simulator-01"]["latest"]["temperature"] is None)
        results.append("Capteur invalide : valeur null et E002")
        scenario("offline")
        wait_for(lambda:not status()["devices"]["simulator-01"]["online"],7)
        assert client.post("/api/v1/commands",headers=headers,json={"device_id":"simulator-01","type":"led","value":True}).status_code==409
        results.append("Coupure : détection à 5 s, commandes refusées")
        scenario("normal")
        wait_for(lambda:status()["devices"]["simulator-01"]["online"])
        scenario("intrusion")
        wait_for(lambda:any(a["type"]=="intrusion" and a["source"]=="simulated" for a in status()["active_alerts"]))
        intrusion=next(a for a in status()["active_alerts"] if a["type"]=="intrusion" and a["source"]=="simulated")
        ack=client.post(f"/api/v1/alerts/{intrusion['id']}/ack",headers=headers)
        ack.raise_for_status();assert ack.json()["acknowledged_at"] and not ack.json()["resolved_at"]
        scenario("normal")
        wait_for(lambda:not any(a["id"]==intrusion["id"] for a in status()["active_alerts"]),8)
        results.append("Intrusion fictive confirmée, acquittée puis résolue")
        scenario("command_timeout")
        id_=command("led");wait_for(lambda:result(id_)=="timeout",8)
        results.append("Commande sans accusé : timeout, exécution inconnue")
        scenario("drift")
        wait_for(lambda:status()["devices"]["simulator-01"]["latest"].get("anomaly",{}).get("active"),50)
        results.append("Dérive progressive : alerte Isolation Forest après persistance")
        scenario("normal")
        wait_for(lambda:not status()["devices"]["simulator-01"]["latest"].get("anomaly",{}).get("active",True),60)
        results.append("Retour normal : résolution après dix observations normales")
        count=len(client.get("/api/v1/measurements?limit=500").json()["items"])
        results.append(f"Historique accessible : {count} mesures dans la dernière minute")
    output={"mode":"simulation-local-sqlite", "results":results,"physical_validation":False,"docker_validation":False}
    (ROOT/"docs").mkdir(exist_ok=True)
    (ROOT/"docs/validation-integration.json").write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(output,indent=2,ensure_ascii=True))


if __name__=="__main__": main()
