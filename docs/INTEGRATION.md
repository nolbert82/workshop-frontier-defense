# Contrat boîtier / backend

## Topics autorisés

Préfixe `sentinel/sentinel-x-01/`. L'appareil publie `telemetry`, `status`, `acks` et reçoit `commands`, `receipts`. QoS 1 partout. Télémétrie, commandes, accusés et reçus **non retenus**. Seul `status` est retenu, avec Last Will `{"state":"offline"}`. Le backend ne considère pas un `status: online` comme une preuve de fraîcheur : une télémétrie actuelle est nécessaire.

## Télémétrie

```json
{
  "device_id": "sentinel-x-01",
  "boot_id": "e04d7392",
  "sequence": 42,
  "uptime_ms": 42000,
  "timestamp": null,
  "temperature": 24.5,
  "humidity": 48.2,
  "gas": 130,
  "presence": false,
  "sensor_age_ms": {"dht22": 1000, "mq2": 0, "pir": 0},
  "sensor_status": {"dht22": "ok", "mq2": "ok", "pir": "ok"},
  "source": "physical",
  "replayed": false,
  "lost_count": 0
}
```

Un message par seconde. DHT22 toutes les deux secondes ; conserver sa dernière valeur avec son âge. États : `ok`, `error`, `stale`, `warming_up`. Un capteur non `ok` émet `null` pour ses valeurs. Gaz : valeur ADC brute 0–4095 (inclut ESP32), sans conversion ppm ; sur ESP8266 le montage doit rester dans sa plage réelle. Température −40–80 °C et humidité 0–100 %. Message MQTT limité à 8192 octets ; champs inconnus refusés. Une date connue doit comporter un fuseau UTC. Sans heure connue, utiliser `null`.

`boot_id` change à chaque démarrage et `sequence` croît. Le backend vérifie l'appareil et la source par le topic autorisé. L'identité `(device_id, boot_id, sequence)` est unique en base. Après transaction validée, il publie :

```json
{"device_id":"sentinel-x-01","boot_id":"e04d7392","sequence":42,"stored":true,"duplicate":false}
```

Le firmware retire une mesure de son tampon uniquement après ce reçu. Un doublon déjà stocké reçoit `duplicate:true`, sans deuxième insertion. Aucun reçu n'est envoyé si la transaction échoue. Les messages rejoués doivent porter **`replayed:true`**, surtout quand l'heure UTC est inconnue. Ils alimentent l'historique sans rafraîchir le direct ni déclencher d'alerte. Le serveur identifie aussi les séquences plus anciennes du même démarrage et les dates de capture périmées.

Le tampon RAM de 60 mesures, la reprise priorisant les nouvelles acquisitions, le débit de rejeu et le compteur de pertes sont à implémenter dans le firmware. La simulation intégrée ne prétend pas émuler une coupure radio réelle avec tampon TLS.

## Commandes et accusés

```json
{"command_id":"UUID","target_boot_id":"e04d7392","expires_at_uptime_ms":47000,"type":"buzzer","value":true,"duration_ms":3000}
```

Types `buzzer` ou `led`. Valeur booléenne explicite, durée entre 100 et 10000 ms. Le boîtier vérifie démarrage et échéance avant toute action. Il conserve vingt résultats et renvoie le même accusé aux doublons sans répéter l'action. La LED système prime sur la LED de test.

```json
{"command_id":"UUID","boot_id":"e04d7392","result":"executed","reason":null}
```

`result` vaut `executed` ou `rejected`, avec une raison courte. Le backend confirme uniquement un identifiant, appareil et démarrage correspondants. Sans réponse en cinq secondes : `timeout`, exécution inconnue. Pas de rejeu automatique après reconnexion ; une commande encore en attente au redémarrage serveur est marquée `timeout`.

## API vision

Le service utilise `Authorization: Bearer VISION_SECRET`. Droits limités à `POST /api/v1/alerts`, `POST /api/v1/vision/heartbeat`, et à la lecture du scénario fictif quand la simulation est activée. Il n'a accès ni aux sessions opérateur, ni à la base, ni à l'API de commande.

```json
{"event_id":"UUID-stable-pour-un-episode","type":"intrusion","state":"active","source":"vision","message":"Personne détectée dans la zone surveillée"}
```

Pour résoudre : même identifiant et `state: resolved`. Les réessais sont idempotents, même après redémarrage du backend. Le heartbeat toutes les secondes indique `camera`, `model`, `median_ms`, `p95_ms`, `simulated`. MJPEG local : `/stream`, secret Bearer requis. FastAPI vérifie la session avant le relais, Nginx publie `/api/v1/video` en HTTPS.

## Séparation des sources

Les commandes et alertes de `simulator-01` restent virtuelles. Une intrusion `source: vision` peut demander un buzzer physique uniquement si l'appareil physique est connecté et MQTT disponible. Une intrusion `source: simulated` vise toujours `simulator-01`. Les incidents sont acquittés et résolus séparément ; l'acquittement ne fait pas disparaître une condition encore active.
